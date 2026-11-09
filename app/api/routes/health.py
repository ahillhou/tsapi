import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/")
def root():
    return {"message": "Voice Automation API Online"}


@router.get("/health")
def health():
    return {"status": "healthy"}


@router.get("/ping")
def ping():
    logger.info("Ping received")
    return {"message": "pong"}
