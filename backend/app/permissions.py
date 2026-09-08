"""Role -> permission codes. Scope is checked separately (see auth.can_access_task)."""

ALL_PERMS = [
    "tasks.read", "tasks.create", "tasks.edit", "tasks.delete", "tasks.assign", "tasks.change_dates",
    "tasks.start", "tasks.submit_review", "tasks.accept", "tasks.return", "tasks.block", "tasks.reopen",
    "tasks.bulk_create", "tasks.export", "checklist.edit", "progress.create", "attachments.upload",
    "attachments.delete", "comments.create", "reports.read",
    "admin.users", "admin.roles", "admin.projects", "admin.task_types", "admin.templates", "admin.bot",
]

# UI da ruxsatlarni guruhlab ko'rsatish uchun (Administratsiya -> Rollar)
PERM_GROUPS = [
    ("tasks", ["tasks.read", "tasks.create", "tasks.edit", "tasks.delete", "tasks.assign", "tasks.change_dates",
               "tasks.bulk_create", "tasks.export"]),
    ("flow", ["tasks.start", "tasks.submit_review", "tasks.accept", "tasks.return", "tasks.block", "tasks.reopen"]),
    ("content", ["checklist.edit", "progress.create", "attachments.upload", "attachments.delete", "comments.create"]),
    ("reports", ["reports.read"]),
    ("admin", ["admin.users", "admin.roles", "admin.projects", "admin.task_types", "admin.templates", "admin.bot"]),
]

ADMIN = [p for p in ALL_PERMS]
RAHBAR = [
    "tasks.read", "tasks.create", "tasks.edit", "tasks.delete", "tasks.assign", "tasks.change_dates",
    "tasks.start", "tasks.submit_review", "tasks.accept", "tasks.return", "tasks.block", "tasks.reopen",
    "tasks.bulk_create", "tasks.export", "checklist.edit", "progress.create", "attachments.upload",
    "attachments.delete", "comments.create", "reports.read", "admin.templates",
]
PRORAB = [
    "tasks.read", "tasks.create", "tasks.edit", "tasks.assign", "tasks.start", "tasks.submit_review",
    "tasks.block", "tasks.export", "checklist.edit", "progress.create", "attachments.upload",
    "comments.create", "reports.read",
]
BAJARUVCHI = [
    "tasks.read", "tasks.start", "tasks.submit_review", "tasks.block", "checklist.edit",
    "progress.create", "attachments.upload", "comments.create",
]
TEKSHIRUVCHI = ["tasks.read", "tasks.accept", "tasks.return", "tasks.export", "comments.create", "reports.read"]
KUZATUVCHI = ["tasks.read", "reports.read"]

SYSTEM_ROLES = [
    ("admin", "Administrator", ADMIN),
    ("rahbar", "Loyiha rahbari", RAHBAR),
    ("prorab", "Prorab", PRORAB),
    ("bajaruvchi", "Bajaruvchi", BAJARUVCHI),
    ("tekshiruvchi", "Tekshiruvchi", TEKSHIRUVCHI),
    ("kuzatuvchi", "Kuzatuvchi", KUZATUVCHI),
]
