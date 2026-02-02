# HU Edge - Intelligent Code Analysis Platform

AI-powered code analysis and chat platform using LangGraph, FastAPI, and Streamlit.

## 🚀 Features

- **Project Upload**: Support for ZIP files and GitHub repositories
- **Repository Intelligence**: Automatic framework and architecture detection
- **Semantic Code Search**: Context-aware search powered by Code-Analyser
- **AI Chat**: Conversational code exploration with LangGraph-based RAG
- **Documentation**: Generate long-form project documentation and export as PDF
- **User Management**: Admin and user roles with JWT authentication
- **Admin Panel**: Admin dashboard at `http://localhost:8501/admin` (admin only)
- **Observability**: Langfuse integration for LLM tracing and monitoring

---

## 📁 Project Structure

```
HU Edge project/
├── backend/              # FastAPI backend application
│   ├── app/
│   │   ├── api/         # API endpoints (v1)
│   │   ├── core/        # Config, security, logging
│   │   ├── models/      # SQLAlchemy ORM models
│   │   ├── schemas/     # Pydantic schemas
│   │   ├── services/    # Business logic (code_analyser, langgraph_rag, etc.)
│   │   ├── db/          # Database utilities
│   │   └── utils/       # Langfuse, helpers
│   ├── Dockerfile
│   └── pyproject.toml
│
├── frontend/            # Streamlit frontend application
│   ├── api/            # Backend API client
│   ├── components/     # Reusable UI components
│   ├── pages/          # Main pages and tabs
│   ├── core/           # Auth, session, logging
│   ├── config/         # Settings
│   ├── utils/          # Helpers
│   ├── Dockerfile
│   └── pyproject.toml
│
├── docker-compose.yml   # Multi-container orchestration
└── .env.example        # Environment variables template
```

---

## 🛠️ Tech Stack

### Backend
- **FastAPI** - Modern, high-performance REST API framework
- **PostgreSQL + pgvector** - Database with vector similarity search
- **LangChain + LangGraph** - Agentic RAG workflow orchestration
- **OpenAI GPT-4** - Language model for code understanding
- **SQLAlchemy 2.0** - Modern ORM with async support
- **Langfuse** - LLM observability and tracing

### Frontend
- **Streamlit** - Rapid web UI development
- **httpx** - Async HTTP client for API communication
- **Python 3.11+** - Modern Python features
- **ReportLab** - PDF export for Documentation tab

---

## 🐳 Quick Start (Docker)

### Prerequisites
- Docker and Docker Compose installed
- OpenAI API key
- Langfuse API keys (optional, for observability)

### 1. Clone Repository

```bash
git clone <repository-url>
cd "HU Edge project"
```

### 2. Environment Setup

Create `.env` file from template:

```bash
cp .env.example .env
```

Edit `.env` and configure:

```bash
# Required
OPENAI_API_KEY=sk-your-openai-api-key-here
SECRET_KEY=your-secret-key-use-openssl-rand-hex-32

# Optional (Langfuse)
LANGFUSE_SECRET_KEY=sk-lf-your-secret-key
LANGFUSE_PUBLIC_KEY=pk-lf-your-public-key
```

**Generate SECRET_KEY:**
```bash
openssl rand -hex 32
```

### 3. Run with Docker Compose

```bash
# Start all services (postgres, backend, frontend)
docker-compose up -d

# View logs
docker-compose logs -f

# View specific service logs
docker-compose logs -f backend
docker-compose logs -f frontend

# Stop services
docker-compose down

# Stop and remove volumes (clean slate)
docker-compose down -v
```

### 4. Access Application

- **Frontend UI**: http://localhost:8501
- **Admin UI**: http://localhost:8501/admin
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### 5. Initialize Database

The database tables are created automatically on first run. To manually initialize:

```bash
# Access backend container
docker-compose exec backend python init_db_script.py
```

---

## 💻 Local Development (Without Docker)

### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -e .

# PostgreSQL (recommended: run pgvector via Docker)
docker run -d \
  --name huedge_postgres \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=huedge_db \
  -p 5432:5432 \
  pgvector/pgvector:pg16

# Create .env file
cp .env.example .env
# Edit .env with your credentials

# Initialize database
python init_db_script.py

# Run backend server
uvicorn app.main:app --reload --port 8000
```

### Frontend Setup

```bash
cd frontend

# Create virtual environment
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -e .

# Create .env file (optional)
echo "FASTAPI_URL=http://localhost:8000" > .env

# Run frontend
streamlit run app.py
```

---

## 📚 API Documentation

Once the backend is running, interactive API documentation is available:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Key Endpoints

#### Authentication
- `POST /signup` - Register new user
- `POST /token` - Login and get JWT token

#### Projects
- `POST /projects/` - Create project (ZIP or GitHub URL)
- `GET /projects/` - List user's projects
- `GET /projects/{id}` - Get project details
- `GET /projects/{id}/analysis` - Get repository intelligence
- `DELETE /projects/{id}` - Delete project

#### Search
- `POST /projects/{id}/search` - Semantic code search

#### Chat
- `POST /chat/projects/{project_id}/sessions` - Create chat session
- `GET /chat/projects/{project_id}/sessions` - List chat sessions
- `POST /chat/sessions/{id}/messages` - Send message (supports `config_id`)
- `GET /chat/sessions/{id}` - Get session with messages

#### Documentation
- `POST /documentation/projects/{project_id}/generate` - Generate and persist documentation (supports `config_id`, `persona_mode`)
- `GET /documentation/projects/{project_id}` - List saved documentation
- `GET /documentation/{doc_id}` - Get a saved documentation

#### Admin
- `GET /admin/analytics` - Basic analytics
- `GET /admin/users` - List all users
- `POST /admin/users` - Create user
- `PUT /admin/users/{user_id}` - Update user
- `DELETE /admin/users/{user_id}` - Delete user
- `GET /admin/projects` - List all projects across users

---

## 🔐 Environment Variables

### Backend (.env)

```bash
# Database
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/huedge_db

# Security
SECRET_KEY=your-secret-key-change-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# OpenAI
OPENAI_API_KEY=sk-your-api-key
OPENAI_EMBEDDING_MODEL=text-embedding-ada-002

# Langfuse (Optional)
LANGFUSE_SECRET_KEY=sk-lf-your-secret
LANGFUSE_PUBLIC_KEY=pk-lf-your-public
LANGFUSE_BASE_URL=https://us.cloud.langfuse.com

# Logging
LOG_LEVEL=INFO
```

### Frontend (.env)

```bash
FASTAPI_URL=http://localhost:8000
LOG_LEVEL=INFO
```

---

## 🗂️ Backend Architecture

### Directory Structure

```
backend/app/
├── api/
│   ├── deps.py              # Dependency injection (auth, db)
│   └── v1/
│       ├── auth.py          # Authentication endpoints
│       ├── projects.py      # Project CRUD endpoints
│       ├── search.py        # Code search endpoints
│       ├── chat.py          # Chat endpoints
│       └── users.py         # User management (admin)
│
├── core/
│   ├── config.py           # Settings and configuration
│   ├── security.py         # JWT, password hashing
│   └── logging.py          # Structured logging setup
│
├── models/
│   ├── user.py             # User ORM model
│   ├── project.py          # Project, File ORM models
│   └── chat.py             # ChatSession, ChatMessage models
│
├── schemas/
│   ├── user.py             # User Pydantic schemas
│   ├── project.py          # Project schemas with validation
│   ├── chat.py             # Chat schemas
│   └── auth.py             # Token schemas
│
├── services/
│   ├── code_analyser.py    # Code analysis workflow
│   ├── langgraph_rag.py    # LangGraph RAG implementation
│   └── repository_analyzer.py # Repository intelligence
│
├── db/
│   ├── session.py          # Database session management
│   └── init_db.py          # Database initialization
│
├── utils/
│   └── langfuse_config.py  # Langfuse tracing setup
│
└── main.py                 # FastAPI application entry point
```

### Key Design Patterns

- **Dependency Injection**: `get_db()`, `get_current_user()`
- **Repository Pattern**: Database access through ORM models
- **Service Layer**: Business logic in `services/`
- **Schema Validation**: Pydantic for request/response validation
- **Middleware**: CORS, logging, exception handling

---

## 🎨 Frontend Architecture

### Directory Structure

```
frontend/
├── api/
│   ├── client.py           # HTTP client configuration
│   ├── auth.py             # Auth API calls
│   ├── projects.py         # Project API calls
│   ├── search.py           # Search API calls
│   ├── chat.py             # Chat API calls
│   └── users.py            # User API calls (admin)
│
├── components/
│   └── sidebar.py          # Navigation sidebar component
│
├── pages/
│   ├── auth_page.py        # Login/Signup page
│   ├── dashboard.py        # Main dashboard
│   └── tabs/
│       ├── projects_tab.py       # Projects list and management
│       ├── create_project_tab.py # Project creation form
│       ├── search_tab.py         # Code search interface
│       └── chat_tab.py           # Chat interface
│
├── core/
│   ├── auth.py             # Auth state management
│   ├── session.py          # Session state utilities
│   └── logging.py          # Logging configuration
│
├── config/
│   └── settings.py         # Application settings
│
└── app.py                  # Streamlit app entry point
```

### Key Features

- **Session State Management**: Centralized auth and UI state
- **Modular Components**: Reusable UI components
- **API Client**: Type-safe HTTP client with error handling
- **Structured Logging**: Consistent logging across modules

---

## 🧪 Testing

### Backend Tests

```bash
cd backend
pytest
```

### Frontend Tests

```bash
cd frontend
pytest
```

---

## 📦 Deployment

### Production Checklist

- [ ] Change `SECRET_KEY` to a strong, unique value
- [ ] Use production-grade PostgreSQL (managed service recommended)
- [ ] Enable HTTPS with SSL/TLS certificates
- [ ] Configure proper CORS origins in backend
- [ ] Set up centralized logging (CloudWatch, ELK, etc.)
- [ ] Configure Langfuse for production monitoring
- [ ] Set appropriate file upload limits
- [ ] Implement backup strategy for database
- [ ] Set up CI/CD pipeline
- [ ] Configure rate limiting
- [ ] Enable security headers
- [ ] Use environment-specific configs

### Docker Production Build

```bash
# Build production images
docker-compose -f docker-compose.prod.yml build

# Run in production mode
docker-compose -f docker-compose.prod.yml up -d
```

---

## 🔧 Troubleshooting

### Database Connection Issues

```bash
# Check PostgreSQL is running
docker-compose ps postgres

# View PostgreSQL logs
docker-compose logs postgres

# Restart PostgreSQL
docker-compose restart postgres
```

### Backend Not Starting

```bash
# Check backend logs
docker-compose logs backend

# Common issues:
# 1. Missing OPENAI_API_KEY in .env
# 2. Database not ready (wait for health check)
# 3. Port 8000 already in use
```

### Frontend Connection Issues

```bash
# Check frontend logs
docker-compose logs frontend

# Verify backend is accessible
curl http://localhost:8000/docs

# Check FASTAPI_URL in frontend environment
docker-compose exec frontend env | grep FASTAPI
```

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

### Code Style

- Follow PEP 8 for Python code
- Use type hints where applicable
- Write docstrings for functions and classes
- Keep functions focused and small
- Add tests for new features

---

## 📄 License

[Add your license here]

---

## 👥 Contact

[Add contact information here]

---

## 🙏 Acknowledgments

- OpenAI for GPT models
- LangChain/LangGraph for RAG framework
- FastAPI for excellent API framework
- Streamlit for rapid UI development
- PostgreSQL team for pgvector extension
