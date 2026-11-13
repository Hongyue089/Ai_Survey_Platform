# AI Survey Platform JSON Generation Instructions

**Applies to AI Survey Platform V2 (2026-11-13).** Give this file and your survey requirements to the AI that will generate the questionnaire. Save the generated output as a UTF-8 `.json` file, then upload it using **Import a Project** on the platform home page. The **Project Name** in the import dialog determines the name of the imported project.

## Instructions for the AI

Generate one project JSON object from the researcher's questions, scales, and routing rules. The project must be importable and runnable in **Preview**. Put the Builder content in `blocks` and the Flow in `flow.elements`. Use IDs to link Flow nodes and conditions to the relevant Builder blocks and questions.

When the researcher supplies exact wording, preserve the question text, response options, scale anchors, and scoring values. If asked to draft questions, follow the requested language and topic. Ask for clarification before generating the file if a missing detail affects the measurement or execution of the survey, such as a scale value, a branch condition, or the experimental groups. Once the requirements are clear, return only one valid JSON object, with no Markdown fences, comments, or explanation. If you can attach a file, name it `survey.json`.

## Top-level fields

| Field | Contents |
|---|---|
| `survey_name` | Recommended. Use a name of up to 100 characters. The import dialog supplies the final project name. |
| `survey_config` | Optional. Typically, set only `general.interface_language` to `en`, `ja`, or `zh-CN`. This controls the interface language. Write the survey questions in the requested language. |
| `blocks` | Array of Builder blocks. |
| `flow` | Object with `schema_version: 1` and an `elements` array. Omit `trash` for a new survey. |
| `ai_configs` | Array of Conversation Agent configurations. If the survey has no AI nodes, use `[]` or omit the field. |

Use standard JSON with double-quoted keys and strings, escaped line breaks (`\n`), lowercase booleans, and no trailing commas. Use only supported fields. Exclude database-generated `survey_id` values, revision history, submitted responses, user permissions, and API keys. The upload limit is 2 MiB.

## IDs and ordering

- Generate a distinct UUID v4 for every block, question, Flow element, Flow path, Question Group, and AI configuration. Their fields are `block_id`, `question_id`, `element_id`, `group_id`, `group_id`, and `ai_config_id`, respectively. Every definition ID in this list must be unique across the file. Use `uuid.uuid4()` if you have a code tool.
- When referencing an element, reuse the UUID from its definition. A block node uses the Builder block's `block_id`. A Branch condition that reads a question uses that question's `question_id`. Keep display names, short labels such as `Q1`, and array indexes out of ID fields.
- Use `choice_id` for answer options or matrix scale points and `statement_id` for matrix rows. Each must be unique within its own list. UUID v4 is also suitable for these IDs. Each option or scale point has an integer `value` that is unique within its list.
- Number `sort_order` from 1 for blocks, for questions within each block, and for Flow nodes within each sibling list. Keep the array order consistent with those numbers. The importer creates the actual database IDs and updates the internal references.

## Builder

Each block contains `block_id`, `block_name`, `sort_order`, and `questions`. Each question contains `question_id`, `question_name`, `question_type`, `question_text`, `sort_order`, `required`, and `config`. Use a unique short label such as `Q1` for `question_name`. Put the respondent-facing wording in `question_text`.

| `question_type` | `config` |
|---|---|
| `multiple_choice` | Set `answer_type` to `single` or `multiple`. Supply a nonempty `choices` array with `choice_id`, integer `value`, and `label` for each option. For multiple selection, specify `min_selection` and `max_selection`. The maximum cannot exceed the number of options. |
| `text_entry` | Set `input_type` to `single_line` or `text_area`. Optionally set `placeholder` and a positive integer `max_characters`. |
| `text_graphic` | Use `config: {}` and `required: false` for instructional text. |
| `matrix` | Set `matrix_type` to `likert` and `answer_type` to `single` or `multiple`. Supply nonempty `statements` and `scale_points` arrays. Each statement has `statement_id` and `label`. Each scale point has `choice_id`, integer `value`, and `label`. |

## Flow

Every node contains `element_id`, `type`, and `sort_order`. Add the configuration and reference fields appropriate to its type. Omit unused fields.

| `type` | Configuration and behavior |
|---|---|
| `block` | Set `block_id` at the node level. The block appears when the Flow reaches this node. |
| `branch` | Put `name`, `routing_mode`, and `condition_groups` in `config`. Each entry in `condition_groups` represents one path and contains its own `children`. |
| `block_randomizer` | Put candidate `block` nodes in the node's `children`. Set `config.randomization_mode` to `select` or `shuffle`. For `select`, set `config.number_to_present`, typically between 1 and 5 and no greater than the number of candidates. `shuffle` shows all candidate blocks in random order. |
| `participant_randomizer` | Set `config.randomization_mode` to `simple` or `balanced`. Define at least two paths in `config.condition_groups`, each with `group_id`, `path_name`, `conditions: []`, and `children`. Each Preview run follows one path. |
| `call_ai` | Set `ai_config_id` at the node level to reference an entry in `ai_configs`. Give each node its own configuration and unique Agent name. |
| `python_code` | Put `name` and `python_code` in `config`. Read an answer with `{#QUESTION_UUID#}` or `response["QUESTION_UUID"]`, using the actual question UUID. Put outputs in a `result` dictionary. A later Branch reads a result with `source_type: "variable"` and the dictionary key. Use simple assignments, conditions, arithmetic, and common conversions. Leave out imports and operations involving files or networks. |
| `end_survey` | Ends the survey early. Optionally set `config.end_information` to display a closing message. The survey also ends normally when the root Flow finishes. |

### Branch paths and conditions

Use `routing_mode: "first"` by default. The Flow evaluates paths in array order and follows the first match. Use `"all"` when the researcher asks to follow every matching path. Each ordinary path has `group_id`, `path_name`, `logic` (`AND` or `OR`), a nonempty `conditions` array, and `children`. An optional fallback path goes last and has `is_default: true` and `conditions: []`. Use at most one fallback.

Each condition has `source_type`, `source_id`, `operator`, and `value`. For a `question` source, use the question UUID. When comparing a multiple-choice answer, use the option's **integer code** as the value. For a `variable` source, use the variable key. For an `agent` source, use its `ai_config_id`.

Supported operators are `equals`, `not_equals`, `contains`, `not_contains`, `greater`, `greater_equal`, `less`, and `less_equal`. Combine all conditions in a path using the path's `logic`. Place referenced questions and agents earlier in the Flow so their data is available when needed. When paths rejoin, avoid referencing answers that exist on only one of those paths.

### Conversation Agents

For each configuration, include `ai_config_id`, `agent_name`, `system_prompt`, `user_message_template`, and a positive integer `max_turns`. In the optional `context_template`, use `{#QUESTION_UUID#}` to reference an earlier answer or `{#AI_CONFIG_UUID#}` to reference an earlier conversation transcript. Replace the placeholders with actual UUIDs. Set `input_source_config.include_previous_conversation: true` to include previous conversations automatically. Use `input_source_config.allow_participant_quit` to control whether the participant can exit the conversation. The platform uses the backend's default model when `model` is omitted. Specify a model only when the researcher has identified one that is available. Generate text-based interview configurations for this version.

## Before returning the JSON

1. Confirm that the file parses as one JSON object and includes Builder blocks and Flow elements.
2. Check that all references resolve within the file, question names and definition IDs are unique, and option codes are integers.
3. Trace each possible route from the start. Confirm that the right blocks appear, referenced data is available, and each Branch leads where expected.
4. Check required questions, wording, language, and scale options against the researcher's instructions. Return only the JSON.

## Importable example

The survey starts by asking whether the respondent would like to answer one more question. **Yes** opens a free-text question. **No** ends the survey. Generate fresh UUIDs for other surveys.

```json
{
  "survey_name": "Sample Feedback Survey",
  "survey_config": {
    "general": {
      "interface_language": "en"
    }
  },
  "blocks": [
    {
      "block_id": "b0a1c001-0000-4000-8000-000000000001",
      "block_name": "Introduction",
      "sort_order": 1,
      "questions": [
        {
          "question_id": "b0a1c001-0000-4000-8000-000000000002",
          "question_name": "Q1",
          "question_type": "multiple_choice",
          "question_text": "Would you like to answer one more question?",
          "sort_order": 1,
          "required": true,
          "config": {
            "answer_type": "single",
            "choices": [
              {
                "choice_id": "yes",
                "value": 1,
                "label": "Yes"
              },
              {
                "choice_id": "no",
                "value": 2,
                "label": "No"
              }
            ]
          }
        }
      ]
    },
    {
      "block_id": "b0a1c001-0000-4000-8000-000000000003",
      "block_name": "Open Feedback",
      "sort_order": 2,
      "questions": [
        {
          "question_id": "b0a1c001-0000-4000-8000-000000000004",
          "question_name": "Q2",
          "question_type": "text_entry",
          "question_text": "What would you most like to see improved?",
          "sort_order": 1,
          "required": false,
          "config": {
            "input_type": "text_area",
            "max_characters": 500
          }
        }
      ]
    }
  ],
  "flow": {
    "schema_version": 1,
    "elements": [
      {
        "element_id": "b0a1c001-0000-4000-8000-000000000005",
        "type": "block",
        "sort_order": 1,
        "block_id": "b0a1c001-0000-4000-8000-000000000001"
      },
      {
        "element_id": "b0a1c001-0000-4000-8000-000000000006",
        "type": "branch",
        "sort_order": 2,
        "config": {
          "name": "Show the Follow-up Question",
          "routing_mode": "first",
          "condition_groups": [
            {
              "group_id": "b0a1c001-0000-4000-8000-000000000007",
              "path_name": "Continue",
              "logic": "AND",
              "conditions": [
                {
                  "source_type": "question",
                  "source_id": "b0a1c001-0000-4000-8000-000000000002",
                  "operator": "equals",
                  "value": 1
                }
              ],
              "children": [
                {
                  "element_id": "b0a1c001-0000-4000-8000-000000000008",
                  "type": "block",
                  "sort_order": 1,
                  "block_id": "b0a1c001-0000-4000-8000-000000000003"
                }
              ]
            }
          ]
        }
      }
    ]
  },
  "ai_configs": []
}
```
