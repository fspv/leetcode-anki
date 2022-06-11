#!/usr/bin/env python3
"""
This script generates an Anki deck with all the leetcode problems currently
known.
"""

import argparse
import asyncio
import logging
from typing import Any, Coroutine, List

# https://github.com/kerrickstaley/genanki
import genanki  # type: ignore
from tqdm import tqdm  # type: ignore

import leetcode_anki.helpers.leetcode

LEETCODE_ANKI_MODEL_ID = 4567610856
LEETCODE_ANKI_DECK_ID = 8589798175
OUTPUT_FILE = "leetcode.apkg"
ALLOWED_EXTENSIONS = {".py", ".go"}


logging.getLogger().setLevel(logging.INFO)


def parse_args() -> argparse.Namespace:
    """
    Parse command line arguments for the script
    """
    parser = argparse.ArgumentParser(description="Generate Anki cards for leetcode")
    parser.add_argument(
        "--start", type=int, help="Start generation from this problem", default=0
    )
    parser.add_argument(
        "--stop", type=int, help="Stop generation on this problem", default=2**64
    )
    parser.add_argument(
        "--page-size",
        type=int,
        help="Get at most this many problems (decrease if leetcode API times out)",
        default=1000,
    )
    parser.add_argument(
        "--list-id",
        type=str,
        help="Get all questions from a specific list id (https://leetcode.com/list?selectedList=<list_id>",
        default="",
    )

    args = parser.parse_args()

    return args


class LeetcodeNote(genanki.Note):
    """
    Extended base class for the Anki note, that correctly sets the unique
    identifier of the note.
    """

    @property
    def guid(self):
        # Hash by leetcode task handle
        return genanki.guid_for(self.fields[0])


async def generate_anki_note(
    leetcode_data: leetcode_anki.helpers.leetcode.LeetcodeData,
    leetcode_model: genanki.Model,
    leetcode_task_handle: str,
) -> LeetcodeNote:
    """
    Generate a single Anki flashcard
    """
    return LeetcodeNote(
        model=leetcode_model,
        fields=[
            leetcode_task_handle,
            str(await leetcode_data.problem_id(leetcode_task_handle)),
            str(await leetcode_data.title(leetcode_task_handle)),
            str(await leetcode_data.category(leetcode_task_handle)),
            await leetcode_data.description(leetcode_task_handle),
            await leetcode_data.difficulty(leetcode_task_handle),
            "yes" if await leetcode_data.paid(leetcode_task_handle) else "no",
            str(await leetcode_data.likes(leetcode_task_handle)),
            str(await leetcode_data.dislikes(leetcode_task_handle)),
            str(await leetcode_data.submissions_total(leetcode_task_handle)),
            str(await leetcode_data.submissions_accepted(leetcode_task_handle)),
            str(
                int(
                    await leetcode_data.submissions_accepted(leetcode_task_handle)
                    / await leetcode_data.submissions_total(leetcode_task_handle)
                    * 100
                )
            ),
            str(await leetcode_data.freq_bar(leetcode_task_handle)),
        ],
        tags=await leetcode_data.tags(leetcode_task_handle),
        # FIXME: sort field doesn't work doesn't work
        sort_field=str(await leetcode_data.freq_bar(leetcode_task_handle)).zfill(3),
    )


async def generate(start: int, stop: int, page_size: int, list_id: str) -> None:
    """
    Generate an Anki deck
    """
    leetcode_model = genanki.Model(
        LEETCODE_ANKI_MODEL_ID,
        "Leetcode model",
        fields=[
            {"name": "Slug"},
            {"name": "Id"},
            {"name": "Title"},
            {"name": "Topic"},
            {"name": "Content"},
            {"name": "Difficulty"},
            {"name": "Paid"},
            {"name": "Likes"},
            {"name": "Dislikes"},
            {"name": "SubmissionsTotal"},
            {"name": "SubmissionsAccepted"},
            {"name": "SumissionAcceptRate"},
            {"name": "Frequency"},
            # TODO: add hints
        ],
        templates=[
            {
                "name": "Leetcode",
                "qfmt": """
                <h2>{{Id}}. {{Title}}</h2>
                <b>Difficulty:</b> {{Difficulty}}<br/>
                &#128077; {{Likes}} &#128078; {{Dislikes}}<br/>
                <b>Submissions (total/accepted):</b>
                {{SubmissionsTotal}}/{{SubmissionsAccepted}}
                ({{SumissionAcceptRate}}%)
                <br/>
                <b>Topic:</b> {{Topic}}<br/>
                <b>Frequency:</b>
                <progress value="{{Frequency}}" max="100">
                {{Frequency}}%
                </progress>
                <br/>
                <b>URL:</b>
                <a href='https://leetcode.com/problems/{{Slug}}/'>
                    https://leetcode.com/problems/{{Slug}}/
                </a>
                <br/>
                <h3>Description</h3>
                {{Content}}
                """,
                "afmt": """
                {{FrontSide}}
                <hr id="answer">
                <b>Discuss URL:</b>
                <a href='https://leetcode.com/problems/{{Slug}}/discuss/'>
                    https://leetcode.com/problems/{{Slug}}/discuss/
                </a>
                <br/>
                <b>Solution URL:</b>
                <a href='https://leetcode.com/problems/{{Slug}}/solution/'>
                    https://leetcode.com/problems/{{Slug}}/solution/
                </a>
                <br/>
                """,
            },
        ],
    )
    leetcode_deck = genanki.Deck(LEETCODE_ANKI_DECK_ID, "leetcode")

    leetcode_data = leetcode_anki.helpers.leetcode.LeetcodeData(start, stop, page_size, list_id)

    note_generators: List[Coroutine[Any, Any, LeetcodeNote]] = []

    task_handles = await leetcode_data.all_problems_handles()

    logging.info("Generating flashcards")
    for leetcode_task_handle in task_handles:
        note_generators.append(
            generate_anki_note(
                leetcode_data,
                leetcode_model,
                leetcode_task_handle,
            )
        )

    for leetcode_note in tqdm(note_generators, unit="flashcard"):
        leetcode_deck.add_note(await leetcode_note)

    genanki.Package(leetcode_deck).write_to_file(OUTPUT_FILE)


async def main() -> None:
    """
    The main script logic
    """
    args = parse_args()

    start, stop, page_size, list_id = args.start, args.stop, args.page_size, args.list_id
    await generate(start, stop, page_size, list_id)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
