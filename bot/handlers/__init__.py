"""Router factories in the order they must be included into the Dispatcher.

System router (start/help/cancel) first so it pre-empts FSM states; role routers next
(admin, tutor, student, then manage = student management shared by tutors and superadmins, after the
student router so ordinary student traffic never pays for its staff lookup); common router last
because it holds the catch-alls.
Routers are created fresh on every call because aiogram routers can be attached to one parent only.
"""

from aiogram import Router

from . import admin, common, manage, student, tutor


def create_routers() -> list[Router]:
    return [
        common.create_system_router(),
        admin.create_router(),
        tutor.create_router(),
        student.create_router(),
        manage.create_router(),
        common.create_common_router(),
    ]


__all__ = ["create_routers"]
