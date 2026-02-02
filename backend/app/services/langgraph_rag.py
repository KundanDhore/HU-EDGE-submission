"""
LangGraph Agentic RAG implementation for code chat.
"""
import os
from typing import Dict, List, Literal, Any, Optional
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.prebuilt import ToolNode, tools_condition

from ..core.logging import get_logger
from ..utils.langfuse_config import get_langfuse_handler

logger = get_logger(__name__)


# Global storage for project_id and db session during graph execution
_current_context = {}


def set_execution_context(project_id: int, db: Session):
    """Set the current execution context for the graph."""
    _current_context['project_id'] = project_id
    _current_context['db'] = db


def get_execution_context():
    """Get the current execution context."""
    return _current_context.get('project_id'), _current_context.get('db')


@tool
def retrieve_code_chunks(query: str) -> str:
    """
    Retrieve relevant code chunks from the project using semantic search.
    Use this tool when you need to find specific code, functions, or implementations.
    
    Args:
        query: The search query describing what code to find
    
    Returns:
        Retrieved code chunks as formatted text
    """
    project_id, db = get_execution_context()
    
    if not project_id or not db:
        logger.error("No execution context set for retrieve_code_chunks")
        return "Error: No project context available"
    
    logger.info(f"Tool called: retrieve_code_chunks | query: '{query}'")
    
    try:
        # Use pgvector-backed semantic search over stored chunks
        from .vector_store import vector_search_project, format_chunks_for_prompt

        chunks = vector_search_project(db=db, project_id=project_id, query=query, k=12)
        if not chunks:
            return "No relevant code chunks found."

        formatted = format_chunks_for_prompt(chunks, max_chars=12000)
        logger.info(f"Vector search retrieved {len(chunks)} chunks")
        return formatted
    
    except Exception as e:
        logger.error(f"Error in retrieve_code_chunks: {e}", exc_info=True)
        return f"Error retrieving code: {str(e)}"


_response_model = None
_grader_model = None


def _get_response_model() -> ChatOpenAI:
    """Lazily construct ChatOpenAI (avoids import-time API key errors)."""
    global _response_model
    if _response_model is None:
        _response_model = ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key=os.getenv("OPENAI_API_KEY"))
    return _response_model


def generate_query_or_respond(state: MessagesState):
    """
    Call the model to generate a response based on the current state.
    Given the question, it will decide to retrieve using the retriever tool,
    or respond directly to the user.
    """
    logger.debug("Node: generate_query_or_respond")
    
    response = (
        _get_response_model()
        .bind_tools([retrieve_code_chunks])
        .invoke(state["messages"])
    )
    
    return {"messages": [response]}


class GradeDocuments(BaseModel):
    """Grade documents using a binary score for relevance check."""
    
    binary_score: str = Field(
        description="Relevance score: 'yes' if relevant, or 'no' if not relevant"
    )


GRADE_PROMPT = (
    "You are a grader assessing relevance of retrieved code chunks to a user question. \n"
    "Here is the retrieved code: \n\n {context} \n\n"
    "Here is the user question: {question} \n"
    "If the code contains keywords or semantic meaning related to the user question, grade it as relevant. \n"
    "Give a binary score 'yes' or 'no' to indicate whether the code is relevant to the question."
)


def _get_grader_model() -> ChatOpenAI:
    """Lazily construct grader model (avoids import-time API key errors)."""
    global _grader_model
    if _grader_model is None:
        _grader_model = ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key=os.getenv("OPENAI_API_KEY"))
    return _grader_model


def grade_documents(
    state: MessagesState,
) -> Literal["generate_answer", "rewrite_question"]:
    """
    Determine whether the retrieved code chunks are relevant to the question.
    """
    logger.debug("Edge: grade_documents")
    
    # Get the original user question
    question = None
    for msg in state["messages"]:
        if isinstance(msg, HumanMessage):
            question = msg.content
            break
    
    if not question:
        logger.warning("No user question found in messages")
        return "generate_answer"
    
    # Get the last tool message (retrieved code)
    context = state["messages"][-1].content
    
    prompt = GRADE_PROMPT.format(question=question, context=context)
    
    try:
        response = (
            _get_grader_model()
            .with_structured_output(GradeDocuments)
            .invoke([{"role": "user", "content": prompt}])
        )
        
        score = response.binary_score
        logger.info(f"Document grade: {score}")
        
        if score == "yes":
            return "generate_answer"
        else:
            return "rewrite_question"
    
    except Exception as e:
        logger.error(f"Error grading documents: {e}", exc_info=True)
        # Default to generating answer if grading fails
        return "generate_answer"


REWRITE_PROMPT = (
    "Look at the input and try to reason about the underlying semantic intent / meaning.\n"
    "Here is the initial question:"
    "\n ------- \n"
    "{question}"
    "\n ------- \n"
    "Formulate an improved question that better captures what the user is looking for:"
)


def rewrite_question(state: MessagesState):
    """
    Rewrite the original user question to improve retrieval.
    """
    logger.debug("Node: rewrite_question")
    
    # Get the original user question
    question = None
    for msg in state["messages"]:
        if isinstance(msg, HumanMessage):
            question = msg.content
            break
    
    if not question:
        logger.warning("No question to rewrite")
        return {"messages": []}
    
    prompt = REWRITE_PROMPT.format(question=question)
    response = _get_response_model().invoke([{"role": "user", "content": prompt}])
    
    logger.info(f"Question rewritten: {question} -> {response.content}")
    
    # Return the rewritten question as a new human message
    return {"messages": [HumanMessage(content=response.content)]}


GENERATE_PROMPT = (
    "You are a helpful AI assistant for answering questions about code. "
    "Use the following retrieved code chunks to answer the question. "
    "If you don't know the answer, just say that you don't know. "
    "Provide clear explanations and reference specific parts of the code when relevant.\n\n"
    "Question: {question}\n\n"
    "Retrieved Code:\n{context}"
)


def generate_answer(state: MessagesState):
    """
    Generate a final answer based on the retrieved code chunks.
    """
    logger.debug("Node: generate_answer")
    
    # Get the original user question
    question = None
    for msg in state["messages"]:
        if isinstance(msg, HumanMessage):
            question = msg.content
            break
    
    # Get the last tool message (retrieved code)
    context = state["messages"][-1].content
    
    prompt = GENERATE_PROMPT.format(question=question, context=context)
    response = _get_response_model().invoke([{"role": "user", "content": prompt}])
    
    logger.info("Generated final answer")
    
    return {"messages": [response]}


# Build the graph
def build_rag_graph():
    """
    Build and compile the LangGraph RAG workflow.
    """
    logger.info("Building LangGraph RAG workflow")
    
    workflow = StateGraph(MessagesState)
    
    # Define nodes
    workflow.add_node("generate_query_or_respond", generate_query_or_respond)
    workflow.add_node("retrieve", ToolNode([retrieve_code_chunks]))
    workflow.add_node("rewrite_question", rewrite_question)
    workflow.add_node("generate_answer", generate_answer)
    
    # Define edges
    workflow.add_edge(START, "generate_query_or_respond")
    
    # Decide whether to retrieve or respond directly
    workflow.add_conditional_edges(
        "generate_query_or_respond",
        tools_condition,
        {
            "tools": "retrieve",
            END: END,
        },
    )
    
    # Grade documents after retrieval
    workflow.add_conditional_edges(
        "retrieve",
        grade_documents,
    )
    
    # After generating answer, end
    workflow.add_edge("generate_answer", END)
    
    # After rewriting question, try generating query again
    workflow.add_edge("rewrite_question", "generate_query_or_respond")
    
    # Compile the graph
    graph = workflow.compile()
    
    logger.info("LangGraph RAG workflow built successfully")
    
    return graph


# Create a singleton instance
_rag_graph = None


def get_rag_graph():
    """Get or create the RAG graph instance."""
    global _rag_graph
    if _rag_graph is None:
        _rag_graph = build_rag_graph()
    return _rag_graph


def run_rag_chat(
    project_id: int,
    message: str,
    db: Session,
    chat_history: Optional[List[Dict[str, str]]] = None
) -> Dict[str, Any]:
    """
    Run the RAG chat for a given message.
    
    Args:
        project_id: Project ID to search within
        message: User message
        db: Database session
        chat_history: Optional previous chat messages
    
    Returns:
        Dictionary with response and metadata
    """
    logger.info(f"Running RAG chat | project: {project_id} | message: '{message}'")
    
    # Set execution context
    set_execution_context(project_id, db)
    
    # Get Langfuse callback handler for the entire RAG workflow
    langfuse_handler = get_langfuse_handler(
        trace_name="rag_chat_workflow",
        metadata={
            "project_id": project_id,
            "message": message[:100],  # Truncate long messages
            "has_history": bool(chat_history)
        },
        tags=["langgraph-rag", "chat", "workflow"]
    )
    
    # Build message history
    messages = []
    
    # Add chat history if provided
    if chat_history:
        for msg in chat_history:
            if msg['role'] == 'user':
                messages.append(HumanMessage(content=msg['content']))
            elif msg['role'] == 'assistant':
                messages.append(AIMessage(content=msg['content']))
    
    # Add current user message
    messages.append(HumanMessage(content=message))
    
    # Get the graph
    graph = get_rag_graph()
    
    # Run the graph with Langfuse callback
    try:
        config = {"callbacks": [langfuse_handler]} if langfuse_handler else {}
        result = graph.invoke({"messages": messages}, config=config)
        
        # Extract the final response
        final_message = result["messages"][-1]
        
        # Check if it's an AI message
        if isinstance(final_message, AIMessage):
            response_content = final_message.content
            
            # Extract retrieved chunks if any tool messages exist
            retrieved_chunks = []
            for msg in result["messages"]:
                if isinstance(msg, ToolMessage):
                    retrieved_chunks.append(msg.content)
            
            logger.info("RAG chat completed successfully")
            
            return {
                "response": response_content,
                "retrieved_chunks": retrieved_chunks if retrieved_chunks else None,
                "success": True
            }
        else:
            logger.warning(f"Unexpected final message type: {type(final_message)}")
            return {
                "response": "I apologize, but I encountered an issue generating a response.",
                "retrieved_chunks": None,
                "success": False
            }
    
    except Exception as e:
        logger.error(f"Error running RAG chat: {e}", exc_info=True)
        return {
            "response": f"I apologize, but I encountered an error: {str(e)}",
            "retrieved_chunks": None,
            "success": False
        }
