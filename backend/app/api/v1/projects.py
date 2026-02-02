"""
Project management endpoints (CRUD, file uploads, analysis).
"""
from typing import List, Optional
from pathlib import Path
import json
import shutil
import zipfile
import subprocess
import uuid
import time
import os
import stat
import urllib.request
import urllib.error
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from starlette.responses import FileResponse

from ...db.session import get_db
from ...api.deps import get_current_user
from ...core.config import settings
from ...core.logging import get_logger
from ... import models, schemas

logger = get_logger(__name__)

router = APIRouter()

MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB
MAX_GITHUB_REPO_SIZE_MB = 100
TEMP_UPLOAD_DIR = Path(settings.PROJECT_FILES_DIR).parent / "temp"
PROJECT_FILES_DIR = Path(settings.PROJECT_FILES_DIR)


def _extract_github_owner_repo(github_url: str) -> Optional[tuple[str, str]]:
    try:
        parsed = urllib.parse.urlparse(github_url)
        if parsed.netloc.lower() != "github.com":
            return None
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) < 2:
            return None
        owner = parts[0]
        repo = parts[1].replace(".git", "")
        if not owner or not repo:
            return None
        return owner, repo
    except Exception:
        return None


def _fetch_github_repo_size_mb(owner: str, repo: str) -> Optional[float]:
    url = f"https://api.github.com/repos/{owner}/{repo}"
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/vnd.github+json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        size_kb = payload.get("size")
        if size_kb is None:
            return None
        return float(size_kb) / 1024.0
    except (urllib.error.HTTPError, urllib.error.URLError, ValueError, json.JSONDecodeError):
        return None


@router.post("/", response_model=schemas.Project)
async def create_project(
    title: str = Form(...),
    description: Optional[str] = Form(None),
    personas: str = Form("[]"),
    zip_file: Optional[UploadFile] = File(None),
    github_url: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(get_current_user)
):
    """Create a new project from ZIP file or GitHub URL"""
    start_time = time.time()
    source_type = "zip" if zip_file else "github" if github_url else "none"
    logger.info(f"Project creation initiated by user: {current_user.email} | title: {title} | source: {source_type}")
    
    if not zip_file and not github_url:
        logger.warning(f"Project creation failed - no source provided | user: {current_user.email}")
        raise HTTPException(status_code=400, detail="Either a ZIP file or a GitHub URL must be provided.")
    if zip_file and github_url:
        logger.warning(f"Project creation failed - both sources provided | user: {current_user.email}")
        raise HTTPException(status_code=400, detail="Only one of ZIP file or GitHub URL can be provided.")

    # Validate personas input
    try:
        personas_list = json.loads(personas)
        if not isinstance(personas_list, list) or not all(isinstance(p, str) for p in personas_list):
            raise ValueError("Personas must be a list of strings.")
        logger.debug(f"Personas validated: {personas_list}")
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"Invalid personas format for user {current_user.email}: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid personas format: {e}")

    project_uuid = str(uuid.uuid4())
    
    # Determine source type and value
    source_type = "zip" if zip_file else "github"
    source_value = zip_file.filename if zip_file else github_url
    
    # Create project in database first to get project_id
    try:
        db_project = models.Project(
            title=title,
            description=description,
            uuid=project_uuid,
            personas=json.dumps(personas_list),
            source_type=source_type,
            source_value=source_value,
            owner_id=current_user.id,
            preprocessing_status="processing"
        )
        db.add(db_project)
        db.commit()
        db.refresh(db_project)
        logger.info(f"Project created in DB | id: {db_project.id} | uuid: {project_uuid}")
    except Exception as e:
        db.rollback()
        logger.error(f"Database error creating project: {e} | user: {current_user.email}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create project in database")
    
    # Now create directory with project_id_{uuid} pattern
    project_path = PROJECT_FILES_DIR / f"{db_project.id}_{project_uuid}"
    project_path.mkdir(parents=True, exist_ok=True)
    logger.info(f"Project directory created: {project_path}")

    if zip_file:
        # Handle ZIP file upload
        file_size_mb = zip_file.size / (1024 * 1024) if zip_file.size else 0
        logger.info(f"Processing ZIP file: {zip_file.filename} | size: {file_size_mb:.2f}MB | user: {current_user.email}")
        
        if zip_file.size and zip_file.size > MAX_FILE_SIZE:
            logger.warning(f"ZIP file too large: {file_size_mb:.2f}MB | max: {MAX_FILE_SIZE / (1024 * 1024)}MB | user: {current_user.email}")
            db.delete(db_project)
            db.commit()
            raise HTTPException(status_code=413, detail=f"File too large. Max size is {MAX_FILE_SIZE / (1024 * 1024)} MB.")
        
        temp_zip_path = TEMP_UPLOAD_DIR / f"{project_uuid}.zip"
        temp_zip_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(temp_zip_path, "wb") as buffer:
                shutil.copyfileobj(zip_file.file, buffer)
            logger.debug(f"ZIP file saved to temp location: {temp_zip_path}")
        except Exception as e:
            logger.error(f"Failed to save ZIP file: {e}", exc_info=True)
            db.delete(db_project)
            db.commit()
            raise HTTPException(status_code=500, detail="Failed to save uploaded file")

        try:
            with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
                zip_ref.extractall(project_path)
            logger.info(f"ZIP extracted successfully to: {project_path}")
        except zipfile.BadZipFile as e:
            logger.error(f"Corrupted ZIP file: {zip_file.filename} | user: {current_user.email} | error: {e}")
            shutil.rmtree(project_path)
            db.delete(db_project)
            db.commit()
            raise HTTPException(status_code=400, detail="Corrupted or incomplete ZIP file.")
        except Exception as e:
            logger.error(f"Error extracting ZIP: {e}", exc_info=True)
            shutil.rmtree(project_path)
            db.delete(db_project)
            db.commit()
            raise HTTPException(status_code=500, detail=f"Error extracting ZIP file: {e}")
        finally:
            temp_zip_path.unlink()
            logger.debug("Temporary ZIP file cleaned up")

        # Basic check for code files
        code_files = [f for f in project_path.rglob('*') if f.is_file() and f.suffix in ['.py', '.js', '.ts', '.java', '.c', '.cpp', '.h']]
        if not code_files:
            logger.warning(f"No code files found in ZIP | user: {current_user.email} | file: {zip_file.filename}")
            shutil.rmtree(project_path)
            db.delete(db_project)
            db.commit()
            raise HTTPException(status_code=422, detail="No recognizable code files found in the ZIP.")
        logger.info(f"Found {len(code_files)} code files in ZIP")

    elif github_url:
        # Handle GitHub URL clone
        logger.info(f"Processing GitHub repository: {github_url} | user: {current_user.email}")
        
        if not github_url.startswith("https://github.com/"):
            logger.warning(f"Invalid GitHub URL format: {github_url} | user: {current_user.email}")
            db.delete(db_project)
            db.commit()
            raise HTTPException(status_code=400, detail="Invalid GitHub URL.")

        owner_repo = _extract_github_owner_repo(github_url)
        if not owner_repo:
            logger.warning(f"Invalid GitHub URL path: {github_url} | user: {current_user.email}")
            db.delete(db_project)
            db.commit()
            raise HTTPException(status_code=400, detail="Invalid GitHub URL.")

        owner, repo = owner_repo
        repo_size_mb = _fetch_github_repo_size_mb(owner, repo)
        if repo_size_mb is None:
            logger.warning(f"Failed to fetch repo size for: {github_url} | user: {current_user.email}")
            db.delete(db_project)
            db.commit()
            raise HTTPException(status_code=502, detail="Unable to check repository size. Please try again.")
        if repo_size_mb > MAX_GITHUB_REPO_SIZE_MB:
            logger.warning(
                f"GitHub repo too large: {repo_size_mb:.1f}MB | limit: {MAX_GITHUB_REPO_SIZE_MB}MB | user: {current_user.email}"
            )
            db.delete(db_project)
            db.commit()
            raise HTTPException(
                status_code=413,
                detail=f"Repository too large ({repo_size_mb:.1f} MB). Max size is {MAX_GITHUB_REPO_SIZE_MB} MB.",
            )

        repo_name = github_url.rstrip('/').split('/')[-1].replace('.git', '')
        clone_path = project_path / repo_name
        logger.debug(f"Clone destination: {clone_path}")
        
        try:
            logger.info(f"Starting git clone for: {github_url}")
            result = subprocess.run(
                ["git", "clone", github_url, str(clone_path)], 
                check=True, 
                capture_output=True, 
                timeout=60
            )
            logger.info(f"Git clone completed successfully for: {github_url}")
            
            # Check if it's an empty repo or non-code repo
            code_files = [f for f in clone_path.rglob('*') if f.is_file() and f.suffix in ['.py', '.js', '.ts', '.java', '.c', '.cpp', '.h']]
            if not code_files:
                logger.warning(f"No code files found in GitHub repo: {github_url} | user: {current_user.email}")
                shutil.rmtree(project_path)
                db.delete(db_project)
                db.commit()
                raise HTTPException(status_code=422, detail="No recognizable code files found in the repository.")
            logger.info(f"Found {len(code_files)} code files in GitHub repository")

        except subprocess.CalledProcessError as e:
            error_output = e.stderr.decode() if e.stderr else "Unknown git error"
            logger.error(f"Git clone failed: {github_url} | error: {error_output} | user: {current_user.email}")
            shutil.rmtree(project_path)
            db.delete(db_project)
            db.commit()
            if "Authentication failed" in error_output or "repository not found" in error_output:
                raise HTTPException(status_code=403, detail="Private repository or access denied.")
            raise HTTPException(status_code=500, detail=f"Failed to clone repository: {error_output}")
        except subprocess.TimeoutExpired:
            logger.error(f"Git clone timeout: {github_url} | user: {current_user.email}")
            shutil.rmtree(project_path)
            db.delete(db_project)
            db.commit()
            raise HTTPException(status_code=504, detail="Repository cloning timed out.")
        except Exception as e:
            logger.error(f"Unexpected error cloning repository: {e}", exc_info=True)
            shutil.rmtree(project_path)
            db.delete(db_project)
            db.commit()
            raise HTTPException(status_code=500, detail=f"Error cloning repository: {e}")

    # Trigger Code-Analyser indexing workflow with progress tracking
    try:
        from ...services.code_analyser import run_indexing_workflow
        from ...services.progress_tracker import ProgressTracker
        
        logger.info(f"Starting Code-Analyser indexing workflow for project {db_project.id}")
        
        # Initialize progress tracker
        progress_tracker = ProgressTracker(db_project.id, db)
        progress_tracker.start_stage('setup', f'Project created: {title}')
        
        # Run indexing with progress tracking
        indexing_results = run_indexing_workflow(db_project.id, project_path, db, progress_tracker)
        logger.info(f"Indexing completed | project: {db_project.id} | results: {indexing_results}")
    except Exception as indexing_error:
        logger.error(f"Indexing failed for project {db_project.id}: {indexing_error}", exc_info=True)
        db_project.preprocessing_status = 'failed'
        db.commit()
    
    elapsed_time = time.time() - start_time
    logger.info(f"Project created successfully | id: {db_project.id} | uuid: {project_uuid} | user: {current_user.email} | duration: {elapsed_time:.2f}s")
    
    return db_project


@router.get("/", response_model=List[schemas.Project])
def read_projects(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(get_current_user)
):
    """Get all projects for current user"""
    logger.debug(f"Fetching projects for user: {current_user.email} | skip: {skip} | limit: {limit}")
    try:
        projects = db.query(models.Project).filter(
            models.Project.owner_id == current_user.id
        ).offset(skip).limit(limit).all()
        logger.info(f"Retrieved {len(projects)} projects for user: {current_user.email}")
        return projects
    except Exception as e:
        logger.error(f"Error fetching projects for user {current_user.email}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve projects")


@router.get("/{project_id}", response_model=schemas.Project)
def read_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(get_current_user)
):
    """Get a specific project"""
    logger.debug(f"Fetching project {project_id} for user: {current_user.email}")
    db_project = db.query(models.Project).filter(
        models.Project.id == project_id,
        models.Project.owner_id == current_user.id
    ).first()
    
    if db_project is None:
        logger.warning(f"Project {project_id} not found for user: {current_user.email}")
        raise HTTPException(status_code=404, detail="Project not found")
    
    logger.debug(f"Project {project_id} retrieved successfully")
    return db_project


@router.delete("/{project_id}")
async def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(get_current_user)
):
    """Delete a project and all its associated data"""
    logger.info(f"Project deletion requested | project: {project_id} | user: {current_user.email}")
    
    # Verify project exists and user owns it
    db_project = db.query(models.Project).filter(
        models.Project.id == project_id,
        models.Project.owner_id == current_user.id
    ).first()
    
    if not db_project:
        logger.warning(f"Project {project_id} not found or unauthorized | user: {current_user.email}")
        raise HTTPException(status_code=404, detail="Project not found")
    
    project_uuid = db_project.uuid
    project_title = db_project.title
    
    try:
        # Delete physical files from disk
        project_path = PROJECT_FILES_DIR / f"{project_id}_{project_uuid}"
        if project_path.exists():
            def handle_remove_readonly(func, path, exc):
                """Handle read-only files on Windows."""
                if not os.access(path, os.W_OK):
                    os.chmod(path, stat.S_IWUSR | stat.S_IRUSR)
                    func(path)
                else:
                    raise
            
            shutil.rmtree(project_path, onerror=handle_remove_readonly)
            logger.info(f"Deleted project files from disk: {project_path}")
        
        # Delete from database (cascades to all related records)
        db.delete(db_project)
        db.commit()
        
        logger.info(f"Project {project_id} deleted successfully | user: {current_user.email}")
        
        return {
            "status": "success",
            "message": f"Project '{project_title}' and all associated data deleted successfully"
        }
    
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting project {project_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete project: {str(e)}")


@router.post("/{project_id}/files/", response_model=schemas.File)
async def upload_file(
    project_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(get_current_user)
):
    """Upload additional files to a project"""
    logger.info(f"File upload initiated | project: {project_id} | file: {file.filename} | user: {current_user.email}")
    
    db_project = db.query(models.Project).filter(
        models.Project.id == project_id,
        models.Project.owner_id == current_user.id
    ).first()
    
    if db_project is None:
        logger.warning(f"File upload failed - project {project_id} not found for user: {current_user.email}")
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        project_dir = Path(f"backend/files/{current_user.id}/{project_id}")
        project_dir.mkdir(parents=True, exist_ok=True)

        file_location = project_dir / file.filename
        with open(file_location, "wb+") as file_object:
            file_object.write(file.file.read())
        logger.debug(f"File saved to: {file_location}")

        db_file = models.File(
            filename=file.filename,
            filepath=str(file_location),
            project_id=project_id
        )
        db.add(db_file)
        db.commit()
        db.refresh(db_file)
        logger.info(f"File uploaded successfully | file_id: {db_file.id} | project: {project_id} | user: {current_user.email}")
        return db_file
    
    except Exception as e:
        db.rollback()
        logger.error(f"Error uploading file: {e} | project: {project_id} | user: {current_user.email}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to upload file")


@router.get("/files/{file_id}")
async def download_file(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(get_current_user)
):
    """Download a file"""
    logger.info(f"File download requested | file_id: {file_id} | user: {current_user.email}")
    
    db_file = db.query(models.File).filter(models.File.id == file_id).first()
    if db_file is None:
        logger.warning(f"File {file_id} not found | user: {current_user.email}")
        raise HTTPException(status_code=404, detail="File not found")

    db_project = db.query(models.Project).filter(
        models.Project.id == db_file.project_id,
        models.Project.owner_id == current_user.id
    ).first()
    
    if db_project is None:
        logger.warning(f"Unauthorized file access attempt | file_id: {file_id} | user: {current_user.email}")
        raise HTTPException(status_code=403, detail="Not authorized to access this file")

    file_path = Path(db_file.filepath)
    if not file_path.exists():
        logger.error(f"File not found on disk | file_id: {file_id} | path: {file_path} | user: {current_user.email}")
        raise HTTPException(status_code=404, detail="File not found on disk")

    logger.info(f"File downloaded successfully | file_id: {file_id} | filename: {db_file.filename} | user: {current_user.email}")
    return FileResponse(file_path, filename=db_file.filename)


@router.get("/{project_id}/analysis")
async def get_project_analysis(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(get_current_user)
):
    """Get repository intelligence analysis for a project"""
    logger.debug(f"Fetching analysis for project {project_id} | user: {current_user.email}")
    
    db_project = db.query(models.Project).filter(
        models.Project.id == project_id,
        models.Project.owner_id == current_user.id
    ).first()
    
    if not db_project:
        logger.warning(f"Project {project_id} not found or unauthorized | user: {current_user.email}")
        raise HTTPException(status_code=404, detail="Project not found")
    
    try:
        entry_points = json.loads(db_project.entry_points) if db_project.entry_points else []
        languages = json.loads(db_project.languages_breakdown) if db_project.languages_breakdown else {}
        dependencies = json.loads(db_project.dependencies) if db_project.dependencies else []
        metadata = json.loads(db_project.analysis_metadata) if db_project.analysis_metadata else {}
        
        analysis = {
            'project_id': project_id,
            'repository_type': db_project.repository_type,
            'framework': db_project.framework,
            'entry_points': entry_points,
            'total_files': db_project.total_files or 0,
            'total_lines_of_code': db_project.total_lines_of_code or 0,
            'languages_breakdown': languages,
            'dependencies': dependencies,
            'api_endpoints_count': db_project.api_endpoints_count or 0,
            'models_count': db_project.models_count or 0,
            'preprocessing_status': db_project.preprocessing_status or 'pending',
            'architecture': metadata.get('architecture'),
            'primary_language': metadata.get('primary_language'),
            'api_endpoints_details': metadata.get('api_endpoints_details', []),
            'models_list': metadata.get('models_list', []),
            'important_files': metadata.get('important_files', [])
        }
        
        logger.info(f"Analysis retrieved for project {project_id}")
        return analysis
    
    except Exception as e:
        logger.error(f"Error fetching analysis for project {project_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve analysis")


@router.get("/{project_id}/progress")
async def get_project_progress(
    project_id: int,
    since_id: int = 0,
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(get_current_user)
):
    """Get latest progress updates for a project (polling endpoint)"""
    logger.debug(f"Fetching progress for project {project_id} since ID {since_id} | user: {current_user.email}")
    
    # Verify project ownership
    db_project = db.query(models.Project).filter(
        models.Project.id == project_id,
        models.Project.owner_id == current_user.id
    ).first()
    
    if not db_project:
        logger.warning(f"Project {project_id} not found or unauthorized | user: {current_user.email}")
        raise HTTPException(status_code=404, detail="Project not found")
    
    try:
        from ...models.project import ProjectProgress
        
        # Get progress records after since_id
        progress_records = db.query(ProjectProgress).filter(
            ProjectProgress.project_id == project_id,
            ProjectProgress.id > since_id
        ).order_by(ProjectProgress.id).limit(50).all()
        
        progress_data = [
            {
                'id': p.id,
                'stage': p.stage,
                'current_file': p.current_file,
                'files_processed': p.files_processed,
                'total_files': p.total_files,
                'percentage': p.percentage,
                'message': p.message,
                'message_type': p.message_type,
                'timestamp': p.timestamp.isoformat() if p.timestamp else None
            }
            for p in progress_records
        ]
        
        return {
            'project_id': project_id,
            'progress': progress_data,
            'current_status': db_project.preprocessing_status
        }
    
    except Exception as e:
        logger.error(f"Error fetching progress for project {project_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve progress")
