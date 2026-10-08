import os
from canvasapi import Canvas


def get_canvas_client() -> Canvas:
    url = os.environ.get("CANVAS_API_URL")
    token = os.environ.get("CANVAS_API_TOKEN")
    if not url or not token:
        raise EnvironmentError(
            "CANVAS_API_URL and CANVAS_API_TOKEN must be set in .env"
        )
    return Canvas(base_url=url, access_token=token)


def get_active_courses(canvas: Canvas) -> list:
    """
    Returns courses where the user is enrolled as a student with an active
    enrollment. Fetches syllabus_body in the same request to avoid extra calls.
    """
    return list(
        canvas.get_courses(
            enrollment_type="student",
            enrollment_state="active",
            include=["syllabus_body"],
        )
    )
