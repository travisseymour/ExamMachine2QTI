#!/usr/bin/env python3

import os
import re
import string
import sys
from collections import namedtuple
from pathlib import Path
from typing import Annotated

import cyclopts
import logzero
from text2qti.config import Config
from text2qti.quiz import Quiz
from text2qti.qti import QTI


log = logzero.setup_logger(name="EM2QTI_Logger", level=logzero.DEBUG)

app = cyclopts.App()

QUESTIONSET = namedtuple("QuestionSet", "question answers points topic")
HEADERINFO = namedtuple("HeaderInfo", "title subtitle instructions")

DEFAULT_TOPIC = "??"


class EM2QTI_FileError(Exception):
    pass


def load_exam(file_path: Path) -> str:
    try:
        text = file_path.read_text(encoding="utf-8-sig")
        text = re.sub(r"\_{3,}", "<code>________</code>", text)
        lines = text.splitlines()
    except FileNotFoundError:
        raise EM2QTI_FileError(f'Could not find exam file "{file_path.as_posix()}"')

    lines = [line for line in lines if line and not line.startswith("#")]
    return "\n".join(lines)


def get_header_info(exam_text: str) -> HEADERINFO:
    title = re.findall(r"^| TITLE: *(.+)", exam_text, flags=re.IGNORECASE)
    subtitle = re.findall(r"^| SUBTITLE: *(.+)", exam_text, flags=re.IGNORECASE)
    instructions = re.findall(r"^| INSTRUCTIONS: *(.+)", exam_text, flags=re.IGNORECASE)

    return HEADERINFO(
        title=title[-1] if title else "",
        subtitle=subtitle[-1] if subtitle else "",
        instructions=instructions[-1] if instructions else "",
    )


def parse_questions(exam_text: str, default_points: float) -> list[QUESTIONSET]:
    q_pattern = re.compile(r"(@ .*[^\$]+)")
    a_pattern = re.compile(r"(\$ .*)+")
    p_pattern = re.compile(r"[ |\|]Points: *([^\|\n\r]+)", re.IGNORECASE)
    t_pattern = re.compile(r"[ |\|]Topic: *([^\|\n\r]+)", re.IGNORECASE)

    exam_text = re.sub(r"([\n\r]*)(@ )", r"\1~THX2249~\n\2", exam_text)
    blocks = [b.strip() for b in exam_text.split("~THX2249~") if b.strip()]

    def make_qa_set(text: str) -> QUESTIONSET:
        match = q_pattern.search(text)
        if not match:
            return QUESTIONSET("", [], 0, "")

        question = match.group()[2:].strip().replace("\r", "\n").replace("\n", "<br>\n")

        answers = [a[2:] for a in a_pattern.findall(text)]

        points_match = p_pattern.search(text)
        topic_match = t_pattern.search(text)

        points = float(points_match.group(1).strip()) if points_match else default_points
        topic = topic_match.group(1).strip() if topic_match else DEFAULT_TOPIC

        question = re.sub(r"\n%.*", "", question)

        return QUESTIONSET(question, answers, points, topic)

    return [q for q in (make_qa_set(b) for b in blocks) if q.question]


def adjust_qa_set(qa_set: QUESTIONSET, number: int) -> QUESTIONSET:
    correct = r"\[ *correct *\]"
    fixed = r"\[ *fixed *\]"
    strip_tags = rf"({correct})|({fixed})"

    question_text = qa_set.question.strip().replace("<br>\n", "<br>")
    question = f"{number}. {question_text}"
    answers = [a.strip() for a in qa_set.answers]

    if answers and not re.search(correct, "\n".join(answers), re.IGNORECASE):
        log.error(f"Question '{question[:40]}...' has no correct answer.")
        sys.exit(1)

    formatted = []
    for i, answer in enumerate(answers):
        label = "*" if re.search(correct, answer, re.IGNORECASE) else ""
        clean = re.sub(strip_tags, "", answer, flags=re.IGNORECASE)
        formatted.append(f"{label}{string.ascii_lowercase[i]}) {clean}")

    if not formatted:
        question += "\n<code>____________</code>"

    return QUESTIONSET(
        question=question,
        answers=formatted,
        points=qa_set.points,
        topic=qa_set.topic,
    )


def add_image_paths(text: str, pic_folder: Path) -> str:
    double_size = re.compile(r"(\[\d+\])(\[\d+\])")
    text = double_size.sub(r"\1", text)

    pic_pattern = re.compile(r"(!\(([^\)]+)\)(\[\d+\])?)")
    base = pic_folder.resolve()

    for full, image, width in pic_pattern.findall(text):
        repl = f"![{image}]({base / image.strip()}){width or ''}"
        text = text.replace(full, repl)

    return text


def txt2qti(source: Path) -> None:
    config = Config()
    text = source.read_text(encoding="utf-8-sig")

    cwd = Path.cwd()
    os.chdir(source.parent)

    try:
        quiz = Quiz(text, config=config, source_name=source.as_posix())
        QTI(quiz).save(source.with_suffix(".zip"))
    finally:
        os.chdir(cwd)


@app.default
def main(
    exam_file: Annotated[Path, cyclopts.Parameter(name="exam_file", help="Path to exam file")],
    default_points: Annotated[float | None, cyclopts.Parameter(help="Default points per question (default: 100/num_questions)")] = None,
    zip_only: Annotated[bool, cyclopts.Parameter(help="Only output the QTI zip file, skip intermediate text file")] = False,
) -> None:
    """Convert ExamMachine-style text exams into QTI packages."""
    exam_file = exam_file.resolve()
    if not exam_file.is_file():
        sys.exit(f"{exam_file} is not a file")

    pic_folder = exam_file.parent / "images"
    if not pic_folder.is_dir():
        pic_folder = exam_file.parent / "pics"
    if not pic_folder.is_dir():
        pic_folder = exam_file.parent
        log.warning("No images/ or pics/ folder found; using exam directory")

    exam_text = load_exam(exam_file)
    header = get_header_info(exam_text)

    exam_text = re.sub(r"\| [^\n\r]*", "", exam_text, flags=re.MULTILINE).strip()

    # First pass to count questions for default points calculation
    raw_questions = parse_questions(exam_text, default_points=0)
    num_questions = len(raw_questions)

    if default_points is None:
        default_points = 100.0 / num_questions if num_questions > 0 else 2.0

    # Re-parse with the actual default points
    qa_sets = [adjust_qa_set(q, i + 1) for i, q in enumerate(parse_questions(exam_text, default_points))]

    output = ""
    output += f"Quiz title: {header.title}\n" if header.title else f"Quiz Title: {exam_file.stem}\n"
    if header.subtitle:
        output += f"Quiz description: {header.subtitle}\n"
    output += "\n"

    for q in qa_sets:
        # text2qti only accepts integer points, so round to nearest int
        points = int(round(q.points))
        output += f"Points: {points}\n{q.question}\n"
        output += "\n".join(q.answers)
        output += "\n\n"

    output = add_image_paths(output, pic_folder)

    out_txt = exam_file.with_name(f"{exam_file.stem}_t2q.txt")

    if not zip_only:
        out_txt.write_text(output)

    # Write temp file for txt2qti, then clean up if zip_only
    if zip_only:
        out_txt.write_text(output)
        txt2qti(out_txt)
        out_txt.unlink()
    else:
        txt2qti(out_txt)


if __name__ == "__main__":
    app()
