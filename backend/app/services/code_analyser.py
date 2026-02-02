"""
Code-Analyser: LangGraph-based incremental code analysis workflow.
Inspired by https://github.com/bhomik749/Code-Analyser
"""
from pathlib import Path
from typing import Dict, List, TypedDict, Annotated, Sequence
import json
from collections import defaultdict

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from sqlalchemy.orm import Session

from ..models.project import Project
from ..core.config import settings
from ..core.logging import get_logger
from ..utils.langfuse_config import get_langfuse_handler
from .repository_analyzer import analyze_repository

logger = get_logger(__name__)


# State schema for the Code-Analyser workflow
class AnalyserState(TypedDict):
    """LangGraph state structure for the Code Analyser workflow."""
    messages: Annotated[Sequence[BaseMessage], add_messages]
    project_id: int
    project_path: str
    repo_tree: Dict
    global_context: str
    selected_files: List[Dict]
    parsed_files: List[Dict]
    all_files: List[Dict]  # All files in the project
    intent: str
    keywords: List[str]
    summary: str
    analysis: Dict  # Repository intelligence analysis
    langfuse_handler: object  # Shared Langfuse handler for all nodes


# Skip patterns
SKIP_PATTERNS = {
    '.git', 'node_modules', '__pycache__', '.venv', 'venv', 'dist', 'build',
    '.next', 'coverage', '.pytest_cache', '.egg-info', '.tox', '.mypy_cache'
}

SKIP_EXTENSIONS = {
    '.min.js', '.map', '.lock', '.log', '.png', '.jpg', '.jpeg',
    '.gif', '.svg', '.ico', '.pdf', '.zip', '.tar', '.gz', '.woff', '.ttf'
}

CODE_EXTENSIONS = {
    '.py', '.js', '.jsx', '.ts', '.tsx', '.java', '.c', '.cpp', '.h', '.hpp',
    '.go', '.rs', '.rb', '.php', '.swift', '.kt', '.cs', '.md', '.json', '.yaml', '.yml'
}

IMPORTANT_FILE_NAMES = [
    'readme', 'main', 'app', 'index', 'config', 'settings', '__init__',
    'server', 'api', 'routes', 'models', 'setup', 'requirements', 'package.json'
]


def fetch_repo_metadata_node(state: AnalyserState) -> Dict:
    """
    Node 1: Fetch repository metadata and build file tree.
    Scans all files and creates a comprehensive tree structure.
    """
    logger.info("=== NODE 1: Fetch Repo Metadata ===")
    
    project_path = Path(state['project_path'])
    
    if not project_path.exists():
        return {
            "repo_tree": {},
            "all_files": [],
            "messages": state["messages"] + [SystemMessage(content="Project path does not exist.")]
        }
    
    try:
        # Build complete file tree
        file_tree = {}
        all_files = []
        
        for file_path in project_path.rglob('*'):
            if file_path.is_file():
                # Skip if in skip directory
                if any(skip_dir in file_path.parts for skip_dir in SKIP_PATTERNS):
                    continue
                
                # Skip by extension
                if file_path.suffix in SKIP_EXTENSIONS:
                    continue
                
                relative_path = file_path.relative_to(project_path)
                ext = file_path.suffix.lower()
                
                # Only include code files
                if ext not in CODE_EXTENSIONS:
                    continue
                
                # Get file size
                try:
                    size = file_path.stat().st_size
                except:
                    size = 0
                
                file_meta = {
                    'path': str(relative_path),
                    'absolute_path': str(file_path),
                    'name': file_path.name,
                    'ext': ext,
                    'size': size,
                    'language': get_language_from_ext(ext)
                }
                
                all_files.append(file_meta)
                
                # Build tree structure
                parts = relative_path.parts
                current = file_tree
                for i, part in enumerate(parts[:-1]):
                    if part not in current:
                        current[part] = {}
                    current = current[part]
                
                current[parts[-1]] = file_meta
        
        logger.info(f"Scanned repository: {len(all_files)} files found")
        
        return {
            "repo_tree": file_tree,
            "all_files": all_files,
            "messages": state["messages"] + [
                SystemMessage(content=f"Fetched metadata for {len(all_files)} files from repository.")
            ]
        }
    
    except Exception as e:
        logger.error(f"Error fetching repo metadata: {e}", exc_info=True)
        return {
            "repo_tree": {},
            "all_files": [],
            "messages": state["messages"] + [SystemMessage(content=f"Error: {str(e)}")]
        }


def global_context_node(state: AnalyserState) -> Dict:
    """
    Node 2: Create global context - high-level understanding of the repository.
    Uses repository analysis and LLM to generate project summary.
    """
    logger.info("=== NODE 2: Global Context Generation ===")
    
    analysis = state.get('analysis', {})
    all_files = state.get('all_files', [])
    
    if not analysis or not all_files:
        return {
            "global_context": "No analysis available",
            "messages": state["messages"] + [SystemMessage(content="No repository analysis available.")]
        }
    
    try:
        # Create context from analysis
        context_parts = [
            f"Repository Type: {analysis.get('repository_type', 'Unknown')}",
            f"Framework: {analysis.get('framework', 'None detected')}",
            f"Primary Language: {analysis.get('primary_language', 'Unknown')}",
            f"Total Files: {len(all_files)}",
            f"Total Lines of Code: {analysis.get('total_lines_of_code', 0)}",
            f"Architecture: {analysis.get('architecture', 'Unknown')}",
        ]
        
        if analysis.get('entry_points'):
            context_parts.append(f"Entry Points: {', '.join(analysis.get('entry_points', []))}")
        
        if analysis.get('api_endpoints_count', 0) > 0:
            context_parts.append(f"API Endpoints: {analysis.get('api_endpoints_count')}")
        
        if analysis.get('models_count', 0) > 0:
            context_parts.append(f"Data Models: {analysis.get('models_count')}")
        
        if analysis.get('dependencies'):
            deps = analysis.get('dependencies', [])[:10]
            context_parts.append(f"Key Dependencies: {', '.join(deps)}")
        
        global_context = "\n".join(context_parts)
        
        # Use LLM to enhance context
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        
        # Use shared Langfuse callback handler from state (if available)
        langfuse_handler = state.get('langfuse_handler')
        
        # If no shared handler, create one for indexing
        if not langfuse_handler:
            project_id = state.get('project_id')
            langfuse_handler = get_langfuse_handler(
                trace_name="global_context_generation",
                metadata={
                    "project_id": project_id,
                    "repository_type": analysis.get('repository_type'),
                    "framework": analysis.get('framework'),
                    "total_files": len(all_files)
                },
                tags=["code-analyser", "global-context", "indexing"]
            )
        
        prompt = f"""Analyze this repository and provide a high-level summary:

{global_context}

Language Breakdown:
{json.dumps(analysis.get('languages_breakdown', {}), indent=2)}

Important Files:
{', '.join(analysis.get('important_files', [])[:10])}

Provide a 2-3 sentence summary of what this project does and its main characteristics."""
        
        # Invoke with Langfuse callback
        config = {"callbacks": [langfuse_handler]} if langfuse_handler else {}
        response = llm.invoke([HumanMessage(content=prompt)], config=config)
        enhanced_context = f"{global_context}\n\nSummary:\n{response.content}"
        
        logger.info("Global context generated successfully")
        
        return {
            "global_context": enhanced_context,
            "messages": state["messages"] + [SystemMessage(content="Global context created.")]
        }
    
    except Exception as e:
        logger.error(f"Error generating global context: {e}", exc_info=True)
        basic_context = "\n".join(context_parts) if 'context_parts' in locals() else "Error generating context"
        return {
            "global_context": basic_context,
            "messages": state["messages"] + [SystemMessage(content=f"Global context created with errors.")]
        }


def analyze_tree_node(state: AnalyserState) -> Dict:
    """
    Node 3: Analyze tree and select important files based on patterns and intent.
    Selects files for parsing based on importance, query keywords, and patterns.
    """
    logger.info("=== NODE 3: Analyze Tree & Select Files ===")
    
    all_files = state.get('all_files', [])
    intent = state.get('intent', 'initial_indexing')
    keywords = state.get('keywords', [])
    
    if not all_files:
        return {
            "selected_files": [],
            "messages": state["messages"] + [SystemMessage(content="No files to analyze.")]
        }
    
    selected_files = []
    selected_paths = set()
    
    # Priority 1: Important file names
    for file_meta in all_files:
        path_lower = file_meta['path'].lower()
        name_lower = file_meta['name'].lower()
        
        # Check if file name contains important keywords
        is_important = any(
            important_name in name_lower or important_name in path_lower
            for important_name in IMPORTANT_FILE_NAMES
        )
        
        if is_important and file_meta['path'] not in selected_paths:
            selected_files.append(file_meta)
            selected_paths.add(file_meta['path'])
    
    # Priority 2: Entry points from analysis
    analysis = state.get('analysis', {})
    entry_points = analysis.get('entry_points', [])
    
    for file_meta in all_files:
        if file_meta['path'] in entry_points and file_meta['path'] not in selected_paths:
            selected_files.append(file_meta)
            selected_paths.add(file_meta['path'])
    
    # Priority 3: Match keywords (if query-driven)
    if keywords:
        for file_meta in all_files:
            path_lower = file_meta['path'].lower()
            if any(kw.lower() in path_lower for kw in keywords):
                if file_meta['path'] not in selected_paths:
                    selected_files.append(file_meta)
                    selected_paths.add(file_meta['path'])
    
    # Priority 4: Small core files (< 50KB)
    for file_meta in all_files:
        if file_meta['size'] < 50000:  # 50KB
            path_parts = file_meta['path'].split('/')
            # Files in root or one level deep
            if len(path_parts) <= 2:
                if file_meta['path'] not in selected_paths:
                    selected_files.append(file_meta)
                    selected_paths.add(file_meta['path'])
    
    # If initial indexing, limit to reasonable number
    if intent == 'initial_indexing' and len(selected_files) > 100:
        selected_files = selected_files[:100]
    
    logger.info(f"Selected {len(selected_files)} files out of {len(all_files)} total files")
    
    return {
        "selected_files": selected_files,
        "messages": state["messages"] + [
            SystemMessage(content=f"Selected {len(selected_files)} important files for parsing.")
        ]
    }


def fetch_and_parse_node(state: AnalyserState) -> Dict:
    """
    Node 4: Fetch and parse selected files.
    Reads file content and creates parsed chunks.
    """
    logger.info("=== NODE 4: Fetch & Parse Files ===")
    
    selected_files = state.get('selected_files', [])
    parsed_files = state.get('parsed_files', [])
    
    if not selected_files:
        return {
            "parsed_files": parsed_files,
            "messages": state["messages"] + [SystemMessage(content="No files to parse.")]
        }
    
    # Get already parsed paths
    parsed_paths = {pf['path'] for pf in parsed_files}
    
    new_parsed = []
    
    for file_meta in selected_files:
        # Skip if already parsed
        if file_meta['path'] in parsed_paths:
            continue
        
        try:
            # Read file content
            with open(file_meta['absolute_path'], 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            if not content.strip():
                continue
            
            # Create parsed file entry
            parsed_entry = {
                'path': file_meta['path'],
                'content': content,
                'language': file_meta['language'],
                'size': file_meta['size'],
                'lines': content.count('\n') + 1
            }
            
            new_parsed.append(parsed_entry)
            parsed_paths.add(file_meta['path'])
            
        except Exception as e:
            logger.error(f"Error parsing file {file_meta['path']}: {e}")
            continue
    
    updated_parsed = parsed_files + new_parsed
    
    logger.info(f"Parsed {len(new_parsed)} new files. Total parsed: {len(updated_parsed)}")
    
    return {
        "parsed_files": updated_parsed,
        "messages": state["messages"] + [
            SystemMessage(content=f"Parsed {len(new_parsed)} files. Total: {len(updated_parsed)}")
        ]
    }


def summarize_repo_node(state: AnalyserState) -> Dict:
    """
    Node 5: Summarize repository based on parsed files and analysis.
    Creates final summary for the indexing phase.
    """
    logger.info("=== NODE 5: Summarize Repository ===")
    
    analysis = state.get('analysis', {})
    parsed_files = state.get('parsed_files', [])
    global_context = state.get('global_context', '')
    
    summary_parts = [
        f"✅ Repository Indexed Successfully",
        f"",
        f"Repository Type: {analysis.get('repository_type', 'Unknown')}",
        f"Framework: {analysis.get('framework', 'Not detected')}",
        f"Primary Language: {analysis.get('primary_language', 'Unknown')}",
        f"",
        f"📊 Statistics:",
        f"  • Total Files Scanned: {analysis.get('total_files', 0)}",
        f"  • Files Parsed: {len(parsed_files)}",
        f"  • Lines of Code: {analysis.get('total_lines_of_code', 0):,}",
        f"  • API Endpoints: {analysis.get('api_endpoints_count', 0)}",
        f"  • Data Models: {analysis.get('models_count', 0)}",
    ]
    
    if analysis.get('entry_points'):
        summary_parts.append(f"  • Entry Points: {', '.join(analysis.get('entry_points', [])[:3])}")
    
    summary = "\n".join(summary_parts)
    
    logger.info("Repository summary created")
    
    return {
        "summary": summary,
        "messages": state["messages"] + [AIMessage(content=summary)]
    }


def get_language_from_ext(ext: str) -> str:
    """Get programming language from file extension."""
    lang_map = {
        '.py': 'python',
        '.js': 'javascript',
        '.jsx': 'javascript',
        '.ts': 'typescript',
        '.tsx': 'typescript',
        '.java': 'java',
        '.c': 'c',
        '.cpp': 'cpp',
        '.h': 'c',
        '.hpp': 'cpp',
        '.go': 'go',
        '.rs': 'rust',
        '.rb': 'ruby',
        '.php': 'php',
        '.swift': 'swift',
        '.kt': 'kotlin',
        '.cs': 'csharp',
        '.md': 'markdown',
        '.json': 'json',
        '.yaml': 'yaml',
        '.yml': 'yaml'
    }
    return lang_map.get(ext.lower(), 'unknown')


# Build the indexing workflow
def create_indexing_workflow() -> StateGraph:
    """Create the LangGraph workflow for repository indexing."""
    
    workflow = StateGraph(AnalyserState)
    
    # Add nodes
    workflow.add_node("fetch_metadata", fetch_repo_metadata_node)
    workflow.add_node("global_context", global_context_node)
    workflow.add_node("analyze_tree", analyze_tree_node)
    workflow.add_node("fetch_and_parse", fetch_and_parse_node)
    workflow.add_node("summarize", summarize_repo_node)
    
    # Add edges
    workflow.add_edge(START, "fetch_metadata")
    workflow.add_edge("fetch_metadata", "global_context")
    workflow.add_edge("global_context", "analyze_tree")
    workflow.add_edge("analyze_tree", "fetch_and_parse")
    workflow.add_edge("fetch_and_parse", "summarize")
    workflow.add_edge("summarize", END)
    
    return workflow.compile()


def query_analyzer_node(state: AnalyserState) -> Dict:
    """
    QA Node 1: Analyze user query to extract intent, keywords, and targets.
    """
    logger.info("=== QA NODE 1: Query Analyzer ===")
    
    messages = state.get('messages', [])
    if not messages:
        return {
            "intent": "unknown",
            "keywords": [],
            "messages": messages
        }
    
    # Get the last user message
    user_query = ""
    for msg in reversed(messages):
        if hasattr(msg, 'type') and msg.type == 'human':
            user_query = msg.content
            break
    
    if not user_query:
        return {
            "intent": "unknown",
            "keywords": [],
            "messages": messages
        }
    
    try:
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        
        # Use shared Langfuse callback handler from state
        langfuse_handler = state.get('langfuse_handler')
        
        prompt = f"""Analyze this user query and extract:
1. Intent: What the user wants to know (e.g., "function_usage", "architecture_summary", "find_file", "explain_code", "how_to")
2. Keywords: Important technical terms or concepts (list 3-5 keywords)

User Query: "{user_query}"

Respond in this format:
Intent: <intent>
Keywords: <keyword1>, <keyword2>, <keyword3>"""
        
        # Invoke with shared Langfuse callback
        config = {"callbacks": [langfuse_handler]} if langfuse_handler else {}
        response = llm.invoke([HumanMessage(content=prompt)], config=config)
        content = response.content
        
        # Parse response
        intent = "unknown"
        keywords = []
        
        for line in content.split('\n'):
            if line.startswith('Intent:'):
                intent = line.replace('Intent:', '').strip().lower()
            elif line.startswith('Keywords:'):
                kw_str = line.replace('Keywords:', '').strip()
                keywords = [kw.strip() for kw in kw_str.split(',') if kw.strip()]
        
        logger.info(f"Query analysis - Intent: {intent}, Keywords: {keywords}")
        
        return {
            "intent": intent,
            "keywords": keywords,
            "messages": messages
        }
    
    except Exception as e:
        logger.error(f"Error analyzing query: {e}", exc_info=True)
        # Extract simple keywords from query
        import re
        words = re.findall(r'\w+', user_query.lower())
        keywords = [w for w in words if len(w) > 3][:5]
        
        return {
            "intent": "search",
            "keywords": keywords,
            "messages": messages
        }


def answer_generation_node(state: AnalyserState) -> Dict:
    """
    QA Node Final: Generate answer based on parsed files and query.
    """
    logger.info("=== QA NODE FINAL: Answer Generation ===")
    
    messages = state.get('messages', [])
    parsed_files = state.get('parsed_files', [])
    global_context = state.get('global_context', '')
    
    # Get user query
    user_query = ""
    for msg in reversed(messages):
        if hasattr(msg, 'type') and msg.type == 'human':
            user_query = msg.content
            break
    
    if not user_query:
        return {
            "messages": messages + [AIMessage(content="No query provided.")]
        }
    
    if not parsed_files:
        return {
            "messages": messages + [AIMessage(content="No relevant files found for your query.")]
        }
    
    try:
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        
        # Use shared Langfuse callback handler from state
        langfuse_handler = state.get('langfuse_handler')
        
        # Prepare context from parsed files
        context_parts = [f"=== Global Context ===\n{global_context}\n"]
        
        for parsed in parsed_files[:15]:  # Limit to top 15 files
            context_parts.append(f"\n=== File: {parsed['path']} ({parsed['language']}) ===")
            # Truncate very long files
            content = parsed['content']
            if len(content) > 10000:
                content = content[:10000] + "\n... (truncated)"
            context_parts.append(content)
        
        full_context = "\n".join(context_parts)
        
        prompt = f"""You are a code analysis assistant. Answer the user's question based on the provided code context.

Context:
{full_context}

User Question: {user_query}


Answer:"""
        
        # Invoke with shared Langfuse callback
        config = {"callbacks": [langfuse_handler]} if langfuse_handler else {}
        response = llm.invoke([HumanMessage(content=prompt)], config=config)
        answer = response.content
        
        logger.info("Answer generated successfully")
        
        return {
            "messages": messages + [AIMessage(content=answer)]
        }
    
    except Exception as e:
        logger.error(f"Error generating answer: {e}", exc_info=True)
        return {
            "messages": messages + [AIMessage(content=f"Error generating answer: {str(e)}")]
        }


# Build the QA workflow
def create_qa_workflow() -> StateGraph:
    """Create the LangGraph workflow for query answering."""
    
    workflow = StateGraph(AnalyserState)
    
    # Add nodes
    workflow.add_node("query_analyzer", query_analyzer_node)
    workflow.add_node("analyze_tree", analyze_tree_node)
    workflow.add_node("fetch_and_parse", fetch_and_parse_node)
    workflow.add_node("answer_generation", answer_generation_node)
    
    # Add edges
    workflow.add_edge(START, "query_analyzer")
    workflow.add_edge("query_analyzer", "analyze_tree")
    workflow.add_edge("analyze_tree", "fetch_and_parse")
    workflow.add_edge("fetch_and_parse", "answer_generation")
    workflow.add_edge("answer_generation", END)
    
    return workflow.compile()


def run_qa_workflow(
    project_id: int,
    query: str,
    db: Session
) -> Dict:
    """
    Run the QA workflow for answering a query about the project.
    
    Args:
        project_id: Database project ID
        query: User query string
        db: Database session
    
    Returns:
        Dictionary with answer and context
    """
    logger.info(f"Starting QA workflow for project {project_id} | query: '{query}'")
    
    try:
        # Get project info
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project {project_id} not found")
        
        # Get project path using new structure: backend/files/projects/{project_id}_{uuid}
        files_dir = Path(settings.PROJECT_FILES_DIR)
        project_dirs = list(files_dir.glob(f"{project_id}_*"))
        if not project_dirs:
            raise ValueError(f"Project directory not found for project {project_id}")
        
        project_path = project_dirs[0]
        logger.info(f"Found project path: {project_path}")
        
        # Get stored analysis
        analysis = {}
        if project.analysis_metadata:
            analysis_meta = json.loads(project.analysis_metadata)
            analysis = {
                'repository_type': project.repository_type,
                'framework': project.framework,
                'entry_points': json.loads(project.entry_points) if project.entry_points else [],
                'total_files': project.total_files,
                'total_lines_of_code': project.total_lines_of_code,
                'languages_breakdown': json.loads(project.languages_breakdown) if project.languages_breakdown else {},
                'dependencies': json.loads(project.dependencies) if project.dependencies else [],
                'api_endpoints_count': project.api_endpoints_count,
                'models_count': project.models_count,
                **analysis_meta
            }
        
        # Create unified Langfuse handler for the entire QA workflow
        langfuse_handler = get_langfuse_handler(
            trace_name="code_qa_workflow",
            metadata={
                "project_id": project_id,
                "query": query,
                "repository_type": project.repository_type,
                "framework": project.framework
            },
            tags=["code-analyser", "qa-workflow", "unified-trace"]
        )
        
        # Create initial state with shared handler
        initial_state: AnalyserState = {
            "messages": [HumanMessage(content=query)],
            "project_id": project_id,
            "project_path": str(project_path),
            "repo_tree": {},
            "global_context": analysis.get('global_context', ''),
            "selected_files": [],
            "parsed_files": [],
            "all_files": [],
            "intent": "",
            "keywords": [],
            "summary": "",
            "analysis": analysis,
            "langfuse_handler": langfuse_handler
        }
        
        # Need to re-fetch file tree for QA
        logger.info("Re-fetching file tree for QA...")
        tree_result = fetch_repo_metadata_node(initial_state)
        initial_state.update(tree_result)
        
        # Run QA workflow
        logger.info("Running QA workflow nodes...")
        workflow = create_qa_workflow()
        final_state = workflow.invoke(initial_state)
        
        # Extract answer
        answer = ""
        for msg in reversed(final_state.get('messages', [])):
            if hasattr(msg, 'type') and msg.type == 'ai':
                answer = msg.content
                break
        
        results = {
            'success': True,
            'answer': answer,
            'files_analyzed': len(final_state.get('parsed_files', [])),
            'intent': final_state.get('intent', ''),
            'keywords': final_state.get('keywords', [])
        }
        
        logger.info(f"QA workflow completed for project {project_id}")
        return results
    
    except Exception as e:
        logger.error(f"Error in QA workflow: {e}", exc_info=True)
        return {
            'success': False,
            'answer': f"Error: {str(e)}",
            'files_analyzed': 0
        }


def run_indexing_workflow(project_id: int, project_path: Path, db: Session, progress_tracker=None) -> Dict:
    """
    Run the complete indexing workflow for a project.
    
    Args:
        project_id: Database project ID
        project_path: Path to the project directory
        db: Database session
        progress_tracker: Optional ProgressTracker instance for real-time updates
    
    Returns:
        Dictionary with workflow results and statistics
    """
    logger.info(f"Starting Code-Analyser indexing workflow for project {project_id}")
    
    try:
        # First, run repository analysis
        logger.info("Running repository analysis...")
        if progress_tracker:
            progress_tracker.start_stage('repository_analysis', 'Analyzing repository structure...')
        
        analysis = analyze_repository(project_path, progress_tracker)
        
        # Create unified Langfuse handler for the entire indexing workflow
        langfuse_handler = get_langfuse_handler(
            trace_name="code_indexing_workflow",
            metadata={
                "project_id": project_id,
                "project_path": str(project_path),
                "repository_type": analysis.get('repository_type'),
                "framework": analysis.get('framework'),
                "total_files": analysis.get('total_files', 0)
            },
            tags=["code-analyser", "indexing-workflow", "unified-trace"]
        )
        
        # Create initial state with shared handler
        initial_state: AnalyserState = {
            "messages": [],
            "project_id": project_id,
            "project_path": str(project_path),
            "repo_tree": {},
            "global_context": "",
            "selected_files": [],
            "parsed_files": [],
            "all_files": [],
            "intent": "initial_indexing",
            "keywords": [],
            "summary": "",
            "analysis": analysis,
            "langfuse_handler": langfuse_handler
        }
        
        # Create and run workflow
        workflow = create_indexing_workflow()
        
        logger.info("Running indexing workflow nodes...")
        if progress_tracker:
            progress_tracker.start_stage('indexing', 'Building code understanding...')
        
        final_state = workflow.invoke(initial_state)
        
        # Store results in database
        logger.info("Storing results in database...")
        if progress_tracker:
            progress_tracker.start_stage('finalizing', 'Saving analysis results...')
        
        # Update project with analysis
        project = db.query(Project).filter(Project.id == project_id).first()
        if project:
            project.repository_type = analysis.get('repository_type')
            project.framework = analysis.get('framework')
            project.entry_points = json.dumps(analysis.get('entry_points', []))
            project.total_files = analysis.get('total_files', 0)
            project.total_lines_of_code = analysis.get('total_lines_of_code', 0)
            project.languages_breakdown = json.dumps(analysis.get('languages_breakdown', {}))
            project.dependencies = json.dumps(analysis.get('dependencies', []))
            project.api_endpoints_count = analysis.get('api_endpoints_count', 0)
            project.models_count = analysis.get('models_count', 0)
            project.analysis_metadata = json.dumps({
                'architecture': analysis.get('architecture'),
                'primary_language': analysis.get('primary_language'),
                'api_endpoints_details': analysis.get('api_endpoints_details', []),
                'models_list': analysis.get('models_list', []),
                'important_files': analysis.get('important_files', []),
                'global_context': final_state.get('global_context', ''),
                'repo_tree_summary': f"{len(final_state.get('all_files', []))} files indexed"
            })
            project.preprocessing_status = 'completed'
            db.commit()

        # Create code chunks + embeddings and store in pgvector
        try:
            from .vector_store import index_project_chunks_to_pgvector

            embed_results = index_project_chunks_to_pgvector(
                project_id=project_id,
                project_root=project_path,
                files=final_state.get("all_files", []),
                db=db,
                progress_tracker=progress_tracker,
            )
            logger.info(
                f"Embedding completed | project: {project_id} | "
                f"chunks: {embed_results.get('chunks_written', 0)} | "
                f"model: {embed_results.get('embedding_model')}"
            )
        except Exception as e:
            logger.error(f"Embedding step failed for project {project_id}: {e}", exc_info=True)
            # Do not fail the whole indexing; fallback is parse-on-demand.
        
        if progress_tracker:
            progress_tracker.complete(f"Project analysis complete! {len(final_state.get('all_files', []))} files indexed")
        
        results = {
            'success': True,
            'project_id': project_id,
            'total_files': len(final_state.get('all_files', [])),
            'parsed_files': len(final_state.get('parsed_files', [])),
            'repository_type': analysis.get('repository_type'),
            'framework': analysis.get('framework'),
            'summary': final_state.get('summary', ''),
            'analysis': analysis
        }
        
        logger.info(f"Indexing workflow completed successfully for project {project_id}")
        return results
    
    except Exception as e:
        logger.error(f"Error in indexing workflow: {e}", exc_info=True)
        
        if progress_tracker:
            progress_tracker.emit_error("Indexing failed", str(e))
        
        # Mark as failed
        project = db.query(Project).filter(Project.id == project_id).first()
        if project:
            project.preprocessing_status = 'failed'
            db.commit()
        
        raise
