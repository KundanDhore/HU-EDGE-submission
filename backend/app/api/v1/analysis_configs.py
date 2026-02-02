"""
API endpoints for analysis configurations (Milestone 4).

These configs control multi-agent chat behavior (depth, verbosity, web augmentation, persona mode).
"""
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...api.deps import get_db, get_current_user
from ...core.logging import get_logger
from ... import models, schemas

logger = get_logger(__name__)

router = APIRouter(prefix="/analysis-configs", tags=["Analysis Configs"])


@router.post("/", response_model=schemas.AnalysisConfig)
def create_analysis_config(
    config: schemas.AnalysisConfigCreate,
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(get_current_user),
):
    logger.info(f"Creating analysis configuration '{config.name}' for user {current_user.email}")

    try:
        if config.is_default:
            db.query(models.AnalysisConfiguration).filter(
                models.AnalysisConfiguration.user_id == current_user.id,
                models.AnalysisConfiguration.is_default == True,
            ).update({"is_default": False})

        db_config = models.AnalysisConfiguration(
            user_id=current_user.id,
            name=config.name,
            is_default=config.is_default,
            analysis_depth=config.analysis_depth,
            doc_verbosity=config.doc_verbosity,
            enable_file_structure_agent=config.enable_file_structure_agent,
            enable_api_agent=config.enable_api_agent,
            enable_web_augmented=config.enable_web_augmented,
            enable_sde_agent=config.enable_sde_agent,
            enable_pm_agent=config.enable_pm_agent,
            persona_mode=config.persona_mode,
            agent_settings=config.agent_settings or {},
        )

        db.add(db_config)
        db.commit()
        db.refresh(db_config)
        return db_config

    except Exception as e:
        db.rollback()
        logger.error(f"Error creating analysis configuration: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create configuration")


@router.get("/", response_model=List[schemas.AnalysisConfig])
def list_analysis_configs(
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(get_current_user),
):
    configs = (
        db.query(models.AnalysisConfiguration)
        .filter(models.AnalysisConfiguration.user_id == current_user.id)
        .order_by(models.AnalysisConfiguration.is_default.desc(), models.AnalysisConfiguration.created_at.desc())
        .all()
    )
    return configs


@router.get("/default", response_model=schemas.AnalysisConfig)
def get_default_config(
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(get_current_user),
):
    config = (
        db.query(models.AnalysisConfiguration)
        .filter(
            models.AnalysisConfiguration.user_id == current_user.id,
            models.AnalysisConfiguration.is_default == True,
        )
        .first()
    )

    if config:
        return config

    # Return system default (not persisted). Must satisfy response_model validation.
    now = datetime.now(timezone.utc)
    return schemas.AnalysisConfig(
        id=0,
        user_id=current_user.id,
        name="System Default",
        is_default=True,
        analysis_depth="standard",
        doc_verbosity="medium",
        enable_file_structure_agent=True,
        enable_api_agent=True,
        enable_web_augmented=False,
        enable_sde_agent=True,
        enable_pm_agent=True,
        persona_mode="both",
        agent_settings={},
        created_at=now,
        updated_at=None,
    )


@router.put("/{config_id}", response_model=schemas.AnalysisConfig)
def update_analysis_config(
    config_id: int,
    config_update: schemas.AnalysisConfigUpdate,
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(get_current_user),
):
    config = (
        db.query(models.AnalysisConfiguration)
        .filter(
            models.AnalysisConfiguration.id == config_id,
            models.AnalysisConfiguration.user_id == current_user.id,
        )
        .first()
    )
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    try:
        if config_update.is_default:
            db.query(models.AnalysisConfiguration).filter(
                models.AnalysisConfiguration.user_id == current_user.id,
                models.AnalysisConfiguration.id != config_id,
                models.AnalysisConfiguration.is_default == True,
            ).update({"is_default": False})

        update_data = config_update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(config, field, value)

        db.commit()
        db.refresh(config)
        return config

    except Exception as e:
        db.rollback()
        logger.error(f"Error updating configuration: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update configuration")


@router.delete("/{config_id}")
def delete_analysis_config(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(get_current_user),
):
    config = (
        db.query(models.AnalysisConfiguration)
        .filter(
            models.AnalysisConfiguration.id == config_id,
            models.AnalysisConfiguration.user_id == current_user.id,
        )
        .first()
    )
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    try:
        db.delete(config)
        db.commit()
        return {"message": "Configuration deleted successfully"}
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting configuration: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete configuration")

