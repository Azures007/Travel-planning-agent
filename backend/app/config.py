from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://travel:travel@localhost:5433/travel_agent"

    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    dashscope_model: str = "qwen-plus"

    # 真实数据 API
    amap_key: str = ""
    qweather_key: str = ""
    # 和风专属 API Host（2026 年起必须用账号专属域名，在控制台「设置→API Host」查看）
    # 示例: https://xxxxxxx.re.qweatherapi.com （weather 和 geo 都用它）
    qweather_host: str = "https://devapi.qweather.com"  # 公共域名已废弃，仅作 fallback
    force_mock_tools: bool = False

    # 上下文压缩（方案3）：估算 token 超过阈值时，把旧对话压缩成摘要
    context_compress_threshold: int = 24000  # 估算 token，超过触发压缩
    context_keep_recent: int = 12            # 压缩时保留最近 N 条消息

    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
