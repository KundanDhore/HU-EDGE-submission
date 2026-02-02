"""
Progress tracking service for real-time updates during project processing.
"""
from sqlalchemy.orm import Session
from typing import Optional
from ..core.logging import get_logger

logger = get_logger(__name__)


class ProgressTracker:
    """Tracks and emits progress updates for project processing"""
    
    def __init__(self, project_id: int, db: Session):
        self.project_id = project_id
        self.db = db
        self.current_stage = None
        self.total_files = 0
        self.files_processed = 0
    
    def set_total_files(self, total: int):
        """Set total number of files to process"""
        self.total_files = total
        logger.info(f"Project {self.project_id}: Total files = {total}")
    
    def start_stage(self, stage: str, message: str):
        """Start a new processing stage"""
        self.current_stage = stage
        self.files_processed = 0
        logger.info(f"Project {self.project_id}: Stage '{stage}' started - {message}")
        self._emit_progress(
            stage=stage,
            message=message,
            percentage=0.0,
            message_type='info'
        )
    
    def update_file_progress(self, filename: str, index: Optional[int] = None):
        """Update progress for current file"""
        if index is not None:
            self.files_processed = index
        else:
            self.files_processed += 1
        
        percentage = (self.files_processed / self.total_files * 100) if self.total_files > 0 else 0
        
        self._emit_progress(
            stage=self.current_stage,
            current_file=filename,
            files_processed=self.files_processed,
            total_files=self.total_files,
            percentage=round(percentage, 1),
            message=f"Processing file {self.files_processed}/{self.total_files}: {filename}",
            message_type='info'
        )
    
    def milestone_complete(self, milestone: str, message: str):
        """Mark a milestone as complete"""
        logger.info(f"Project {self.project_id}: Milestone '{milestone}' complete - {message}")
        percentage = round((self.files_processed / self.total_files * 100), 1) if self.total_files > 0 else 100
        self._emit_progress(
            stage=self.current_stage,
            message=f"✓ {milestone}: {message}",
            percentage=percentage,
            message_type='success'
        )
    
    def emit_info(self, message: str):
        """Emit an info message"""
        logger.info(f"Project {self.project_id}: {message}")
        self._emit_progress(
            stage=self.current_stage,
            message=message,
            message_type='info'
        )
    
    def emit_warning(self, message: str, details: Optional[str] = None):
        """Emit a warning message"""
        full_message = f"⚠️ {message}"
        if details:
            full_message += f": {details}"
        logger.warning(f"Project {self.project_id}: {full_message}")
        self._emit_progress(
            stage=self.current_stage,
            message=full_message,
            message_type='warning'
        )
    
    def emit_error(self, message: str, details: Optional[str] = None):
        """Emit an error message"""
        full_message = f"❌ {message}"
        if details:
            full_message += f": {details}"
        logger.error(f"Project {self.project_id}: {full_message}")
        self._emit_progress(
            stage=self.current_stage,
            message=full_message,
            message_type='error'
        )
    
    def complete(self, message: str = "Processing complete"):
        """Mark entire process as complete"""
        logger.info(f"Project {self.project_id}: Complete - {message}")
        self._emit_progress(
            stage='completed',
            message=f"✅ {message}",
            percentage=100.0,
            message_type='success'
        )
    
    def _emit_progress(
        self,
        stage: str,
        message: str,
        current_file: Optional[str] = None,
        files_processed: Optional[int] = None,
        total_files: Optional[int] = None,
        percentage: float = 0.0,
        message_type: str = 'info'
    ):
        """Save progress to database"""
        try:
            from ..models.project import ProjectProgress
            
            progress = ProjectProgress(
                project_id=self.project_id,
                stage=stage,
                current_file=current_file,
                files_processed=files_processed or self.files_processed,
                total_files=total_files or self.total_files,
                percentage=percentage,
                message=message,
                message_type=message_type
            )
            self.db.add(progress)
            self.db.commit()
            logger.debug(f"Progress emitted: {stage} - {message}")
        except Exception as e:
            logger.error(f"Failed to emit progress: {e}")
            self.db.rollback()
