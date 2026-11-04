# src/domain/enums.py
from enum import Enum

class TaskType(str, Enum):
    # 任务类型枚举
    AI_TRAINING = "ai_training"       # AI训练（长时、高算力、可中断）
    SCIENTIFIC = "scientific"         # 科学计算（高内存带宽、突发性）
    RENDERING = "rendering"           # 渲染/视频转码（吞吐量大、延迟敏感）
    WEB_SERVICE = "web_service"       # 通用Web服务（低算力、实时性高）
    GENERAL = "general"               # 通用计算（其他）


class TaskStatus(str, Enum):
    SUBMITTED = "submitted"
    PENDING = "pending"
    READY = "ready"
    SCHEDULING = "scheduling"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
