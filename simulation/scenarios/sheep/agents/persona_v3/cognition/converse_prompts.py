from datetime import datetime

import numpy as np

from simulation.persona.common import PersonaIdentity
from simulation.utils import ModelWandbWrapper
from pathfinder import assistant, system, user

from .utils import (
    consider_identity_persona_prompt,
    conversation_to_string_with_dash,
    get_sytem_prompt,
    list_to_comma_string,
    list_to_string_with_dash,
    location_time_info,
    memory_prompt,
    reasoning_steps_prompt,
)


def prompt_converse_utterance_in_group(
    model: ModelWandbWrapper,
    init_persona: PersonaIdentity,
    target_personas: list[PersonaIdentity],
    init_retrieved_memory: list[str],
    current_location: str,
    current_time: datetime,
    current_context: str,
    current_conversation: list[tuple[str, str]],
) -> tuple[str, bool, str]:
    lm = model.start_chain(
        init_persona.name, "cognition_converse", "converse_utterance"
    )

    # Only the other participants can speak next (never the Mayor or oneself).
    names = [t.name for t in target_personas]
    speaker_options = [n for n in names if n != init_persona.name]
    # Fallback if the model's answer cannot be parsed: next person in the circle,
    # so a failure does not always favour the same persona.
    fallback_speaker = names[(names.index(init_persona.name) + 1) % len(names)]

    with user():
        lm += f"{get_sytem_prompt(init_persona)}\n"
        lm += location_time_info(current_location, current_time)
        # List key memories of the initial persona
        lm += memory_prompt(init_persona, init_retrieved_memory)
        # Provide the current context
        lm += "\n"
        # lm += f"Current context: {current_context}\n\n"
        # Describe the group chat scenario
        lm += (
            f"Scenario: {list_to_comma_string([t.name for t in target_personas])} are "
            "engaged in a group chat."
        )
        lm += "\nConversation so far:\n"
        lm += f"{conversation_to_string_with_dash(current_conversation)}\n\n"
        # Define the task for the language model
        lm += (
            f"Task: What would you say next in the group chat? "
            "Ensure the conversation flows naturally and avoids repetition. "
            "Determine if your response concludes the conversation. "
            "If not, identify the next speaker. "
            "The Mayor only reads the monthly report and does not take part; "
            "choose the next speaker from the shepherds listed in the scenario.\n\n"
        )
        # Define the format for the output
        REPONSE = "Response: "
        ANSWER_STOP = "Conversation conclusion by me: "
        NEXT_SPEAKER = "Next speaker: "

        lm += "Output format:\n"
        lm += REPONSE + "[fill in]\n"
        lm += ANSWER_STOP + "[yes/no]\n"
        lm += NEXT_SPEAKER + f"[one of: {', '.join(speaker_options)}]\n"
    with assistant():
        lm += REPONSE
        lm = model.gen(
            lm,
            name="utterance",
            default_value="",
            stop_regex=r"Conversation conclusion by me:",  # name can be mispelled by LLM sometimes
        )
        utterance = lm["utterance"].strip()
        if len(utterance) > 0 and utterance[-1] == '"' and utterance[0] == '"':
            utterance = utterance[1:-1]
        lm += ANSWER_STOP
        lm = model.select(
            lm,
            name="utterance_ended",
            options=["yes", "no", "No", "Yes"],
            default_value="yes",
        )
        utterance_ended = lm["utterance_ended"].lower() == "yes"

        if utterance_ended:
            next_speaker = None
        else:
            lm += "\n"
            lm += NEXT_SPEAKER
            lm = model.select(
                lm,
                name="next_speaker",
                options=speaker_options,
                default_value=fallback_speaker,
            )
            assert lm["next_speaker"] in speaker_options
            next_speaker = lm["next_speaker"]

    model.end_chain(init_persona.name, lm)
    return utterance, utterance_ended, next_speaker, lm.html()


def prompt_summarize_conversation_in_one_sentence(
    model: ModelWandbWrapper,
    conversation: list[tuple[str, str]],
):
    lm = model.start_chain(
        "framework",
        "cognition_converse",
        "prompt_summarize_conversation_in_one_sentence",
    )

    with user():
        lm += f"Conversation:\n"
        lm += f"{conversation_to_string_with_dash(conversation)}\n\n"
        lm += "Summarize the conversation above in one sentence."
    with assistant():
        lm = model.gen(lm, name="summary", default_value="", stop_regex=r"\.")
        summary = lm["summary"] + "."

    model.end_chain("framework", lm)
    return summary, lm.html()
