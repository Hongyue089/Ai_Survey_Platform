from typing import Literal, Any
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, model_validator, AliasChoices


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


ID = str


class Choice(Strict):
    choice_id: ID = Field(min_length=1, max_length=64)
    value: int
    label: str = Field(default="", max_length=10000)


class Statement(Strict):
    statement_id: ID = Field(min_length=1, max_length=64)
    label: str = Field(default="", max_length=10000)


class ResponseTimeConfig(Strict):
    enabled: bool = False
    start_timing: Literal["page_displayed"] = "page_displayed"
    end_timing: Literal["first_interaction", "final_response"] = "final_response"


class MCConfig(Strict):
    response_time: ResponseTimeConfig = Field(default_factory=ResponseTimeConfig)
    answer_type: Literal["single", "multiple"] = "single"
    format: Literal["list", "dropdown"] = "list"
    layout: Literal["vertical", "horizontal", "2_columns", "3_columns"] = "vertical"
    min_selection: int = Field(default=1, ge=0)
    max_selection: int = Field(default=1, ge=1)
    choices: list[Choice] = Field(min_length=1)

    @model_validator(mode="after")
    def check(self):
        if self.answer_type == "single":
            self.min_selection = self.max_selection = 1
        if self.min_selection > self.max_selection or self.max_selection > len(
            self.choices
        ):
            raise ValueError("Invalid selection range")
        if len({c.choice_id for c in self.choices}) != len(self.choices) or len(
            {c.value for c in self.choices}
        ) != len(self.choices):
            raise ValueError("Duplicate choice identity")
        return self


class TextConfig(Strict):
    input_type: Literal["single_line", "text_area"] = "single_line"
    placeholder: str = ""
    max_characters: int = Field(default=1000, ge=1, le=100000)


class MatrixConfig(Strict):
    matrix_type: Literal["likert"] = "likert"
    answer_type: Literal["single", "multiple"] = "single"
    statements: list[Statement] = Field(min_length=1)
    scale_points: list[Choice] = Field(min_length=1)

    @model_validator(mode="after")
    def check(self):
        if len({s.statement_id for s in self.statements}) != len(self.statements):
            raise ValueError("Duplicate statement identity")
        if len({c.choice_id for c in self.scale_points}) != len(
            self.scale_points
        ) or len({c.value for c in self.scale_points}) != len(self.scale_points):
            raise ValueError("Duplicate scale identity")
        return self


class QuestionData(Strict):
    question_id: ID = Field(min_length=1, max_length=64)
    question_name: str = Field(min_length=1, max_length=255)
    question_type: Literal["multiple_choice", "text_entry", "text_graphic", "matrix"]
    question_text: str = Field(default="", max_length=100000)
    sort_order: int = Field(ge=0)
    required: bool = False
    config: dict[str, Any] = Field(default_factory=dict)
    is_deleted: bool = False
    deleted_at: datetime | None = None

    @model_validator(mode="after")
    def check(self):
        cls = {
            "multiple_choice": MCConfig,
            "text_entry": TextConfig,
            "matrix": MatrixConfig,
        }.get(self.question_type)
        if cls:
            self.config = cls.model_validate(self.config).model_dump()
        elif self.config:
            raise ValueError("Text/Graphic config must be empty")
        if self.question_type == "text_graphic":
            self.required = False
        return self


class QuestionGroup(Strict):
    group_id: str = Field(min_length=1, max_length=64)
    name: str = Field(default="Question Group", min_length=1, max_length=255)
    question_ids: list[str] = Field(default_factory=list)
    question_order: Literal["original", "random"] = "original"
    display_mode: Literal["all", "random_n"] = "all"
    display_count: int = Field(default=1, ge=1)


class BlockData(Strict):
    question_groups: list[QuestionGroup] = Field(default_factory=list)
    block_id: ID = Field(min_length=1, max_length=64)
    block_name: str = Field(min_length=1, max_length=255)
    sort_order: int = Field(ge=0)
    is_deleted: bool = False
    deleted_at: datetime | None = None
    questions: list[QuestionData] = Field(default_factory=list)


class Condition(Strict):
    source_type: Literal["question", "variable", "agent"] = "question"
    source_id: str = ""
    operator: Literal["equals", "not_equals", "contains", "not_contains", "greater", "greater_equal", "less", "less_equal"] = "equals"
    value: Any = ""
    connector: Literal["AND", "OR"] = "AND"


class ConditionGroup(Strict):
    group_id: str
    path_name: str = Field(default="", max_length=255)
    logic: Literal["AND", "OR"] | None = None
    is_default: bool = False
    connector: Literal["AND", "OR"] = "AND"
    conditions: list[Condition] = Field(
        default_factory=lambda: [Condition()]
    )
    children: list["FlowElement"] = Field(default_factory=list)


class ElementConfig(Strict):
    name: str = ""
    end_information: str = Field(default="", max_length=100000)
    condition_groups: list[ConditionGroup] = Field(default_factory=list)
    number_to_present: int = Field(default=1, ge=1)
    evenly_present: bool = False
    routing_mode: Literal["first", "all"] | None = None
    randomization_mode: Literal["select", "shuffle", "simple", "balanced"] | None = None
    python_code: str = Field(default="", max_length=32768)
    variable_name: str = ""
    value: Any = ""


class FlowElement(Strict):
    element_id: str = Field(min_length=1, max_length=64, validation_alias=AliasChoices("element_id", "node_id"))
    type: Literal[
        "block", "branch", "randomizer", "block_randomizer", "participant_randomizer", "python_code", "embedded_data", "call_ai", "end_survey"
    ]
    sort_order: int = Field(ge=0)
    block_id: str | None = None
    ai_config_id: str | None = None
    config: ElementConfig = Field(default_factory=ElementConfig)
    children: list["FlowElement"] = Field(default_factory=list)

    @model_validator(mode="after")
    def check(self):
        if self.type not in ("randomizer", "block_randomizer") and self.children:
            raise ValueError(
                "Only Randomizer has direct children; Branch uses condition group paths"
            )
        if self.type not in ("branch", "participant_randomizer") and self.config.condition_groups:
            raise ValueError("Only Branch has condition groups")
        return self


ConditionGroup.model_rebuild()
FlowElement.model_rebuild()


class FlowTrash(Strict):
    element: FlowElement
    parent_id: str | None = None
    group_id: str | None = None
    position: int = Field(ge=0)
    deleted_at: datetime


class FlowData(Strict):
    schema_version: Literal[1] = 1
    elements: list[FlowElement] = Field(default_factory=list)
    trash: list[FlowTrash] = Field(default_factory=list)


class GeneralOptions(Strict):
    interface_language: Literal["en", "ja", "zh-CN"] = "ja"
    display_name: str = Field(default="", max_length=255)
    survey_description: str = Field(default="", max_length=10000)
    show_question_numbers: bool = False


class IncompleteOptions(Strict):
    action: Literal["record", "delete"] = "record"
    timeout_days: int = Field(default=7, ge=1)


class ResponseOptions(Strict):
    allow_back_button: bool = True
    allow_finish_later: bool = True
    incomplete_response: IncompleteOptions = Field(default_factory=IncompleteOptions)


class AvailabilityOptions(Strict):
    open_at: datetime | None = None
    close_at: datetime | None = None

    @model_validator(mode="after")
    def check(self):
        if self.open_at and self.open_at.tzinfo is None:
            raise ValueError("Timezone required for open_at")
        if self.close_at and self.close_at.tzinfo is None:
            raise ValueError("Timezone required for close_at")
        if self.open_at and self.close_at and self.close_at <= self.open_at:
            raise ValueError("close_at must follow open_at")
        return self


class ReferrerOptions(Strict):
    enabled: bool = False
    domains: list[str] = Field(default_factory=list)


class SecurityOptions(Strict):
    allowed_referrer: ReferrerOptions = Field(default_factory=ReferrerOptions)
    prevent_multiple_submissions: bool = True
    bot_detection_enabled: Literal[False] = False
    prevent_search_indexing: bool = True
    anonymize_responses: bool = True


class AIOptions(Strict):
    enabled: bool = False
    config_id: str | None = None


class SurveyOptions(Strict):
    general: GeneralOptions = Field(default_factory=GeneralOptions)
    responses: ResponseOptions = Field(default_factory=ResponseOptions)
    availability: AvailabilityOptions = Field(default_factory=AvailabilityOptions)
    security: SecurityOptions = Field(default_factory=SecurityOptions)
    ai: AIOptions = Field(default_factory=AIOptions)


class LoggingConfig(Strict):
    save_prompt: bool = True
    save_response: bool = True
    save_token_usage: bool = True
    save_latency: bool = True
    save_error: bool = True


class InputSource(Strict):
    question_id: str | None = None
    include_previous_conversation: bool = False
    allow_participant_quit: bool = True


class AIConfigData(Strict):
    agent_type: Literal["conversation"] = "conversation"
    ai_config_id: str = Field(min_length=1, max_length=64)
    config_name: str = Field(default="Conversation", min_length=1, max_length=255)
    config_version: int = Field(default=1, ge=1)
    agent_name: str = Field(default="Conversation_1", min_length=1, max_length=255)
    provider: Literal["openai"] = "openai"
    model: str = Field(default="", max_length=128)
    system_prompt: str = Field(default="", max_length=100000)
    context_template: str = Field(default="", max_length=100000)
    user_message_template: str = Field(default="", max_length=100000)
    input_source_config: InputSource = Field(default_factory=InputSource)
    temperature: float = Field(default=0.7, ge=0, le=1)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_output_tokens: int = Field(default=800, ge=1)
    max_turns: int = Field(default=3, ge=1)
    include_history: bool = True
    history_window: int | None = Field(default=10, ge=0)
    end_condition: Literal["max_turns_reached"] = "max_turns_reached"
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    max_retries: int = Field(default=2, ge=0, le=5)
    failure_behavior: Literal[
        "skip", "show_error", "use_default_value", "end_survey"
    ] = "show_error"
    response_format: Literal["text", "json"] = "text"
    logging_config: LoggingConfig = Field(default_factory=LoggingConfig)


class WorkingData(Strict):
    survey_name: str = Field(min_length=1, max_length=100)
    survey_config: SurveyOptions = Field(default_factory=SurveyOptions)
    blocks: list[BlockData] = Field(default_factory=list)
    flow: FlowData = Field(default_factory=FlowData)
    ai_configs: list[AIConfigData] = Field(default_factory=list)


class SaveRequest(WorkingData):
    expected_version: int = Field(ge=1)
    save_type: Literal["auto", "apply"] = "apply"


class RestoreRequest(Strict):
    expected_version: int = Field(ge=1)


class TimingEvent(Strict):
    question_id: str
    event: Literal["question_displayed", "option_selected", "page_submitted"]
    at: datetime
    elapsed_ms: float = Field(ge=0, le=86400000)
    value: Any = None


class PageTiming(Strict):
    question_id: str
    events: list[TimingEvent] = Field(max_length=10000)


class SubmitAnswers(Strict):
    answers: dict[str, Any]
    timings: list[PageTiming] = Field(default_factory=list)


class ChatRequest(Strict):
    message: str = Field(default="", max_length=100000)


class WorkingView(WorkingData):
    survey_id: str
    project_type: Literal["survey"]
    status: Literal["draft", "published", "closed"]
    working_version: int
    updated_at: datetime
    created_at: datetime
    role: Literal["owner", "editor", "viewer"]


class ProjectView(Strict):
    survey_id: str
    project_type: Literal["survey"]
    survey_name: str
    status: Literal["draft", "published", "closed"]
    created_at: datetime
    updated_at: datetime
    question_count: int
    response_count: int


class ProjectPage(Strict):
    items: list[ProjectView]
    page: int
    page_size: int
    total: int


class AIConfigRequest(Strict):
    expected_version: int = Field(ge=1)
    config: AIConfigData


class ImportRequest(Strict):
    import_request_id: str
    project_name: str
    file_name: str
    content: str
