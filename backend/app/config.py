from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://survey:survey@127.0.0.1:5432/survey"
    dev_user_id: str = "dev_admin"
    development_mode: bool = True
    cors_origin: str = "http://localhost:5173"
    openai_api_key: str = ""
    ai_model: str = ""
    ai_api_url: str = "https://api.openai.com/v1/chat/completions"


settings = Settings()


def default_options():
    return {
        "general": {
            "interface_language": "ja",
            "display_name": "",
            "survey_description": "",
            "show_question_numbers": False,
        },
        "responses": {
            "allow_back_button": True,
            "allow_finish_later": True,
            "incomplete_response": {"action": "record", "timeout_days": 7},
        },
        "availability": {"open_at": None, "close_at": None},
        "security": {
            "allowed_referrer": {"enabled": False, "domains": []},
            "prevent_multiple_submissions": True,
            "bot_detection_enabled": False,
            "prevent_search_indexing": True,
            "anonymize_responses": True,
        },
        "ai": {"enabled": False, "config_id": None},
    }
