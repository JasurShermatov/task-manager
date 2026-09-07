from fastapi import HTTPException


class ApiError(HTTPException):
    def __init__(self, status: int, code: str, message: str, field_errors: dict | None = None, **extra):
        super().__init__(status_code=status, detail={"code": code, "message": message,
                                                     "field_errors": field_errors or {}, **extra})
        self.code = code


def unauthorized(msg="Sessiya tugadi. Qaytadan kiring."):
    return ApiError(401, "UNAUTHORIZED", msg)


def scope_forbidden():
    return ApiError(403, "SCOPE_FORBIDDEN", "Bu vazifa sizning doirangizga kirmaydi.")


def permission_denied():
    return ApiError(403, "PERMISSION_DENIED", "Bu amal uchun ruxsatingiz yo'q.")


def task_not_found():
    return ApiError(404, "TASK_NOT_FOUND", "Vazifa topilmadi yoki arxivlangan.")


def not_found(what="Obyekt"):
    return ApiError(404, "NOT_FOUND", f"{what} topilmadi.")


def version_conflict():
    return ApiError(409, "VERSION_CONFLICT", "Vazifa boshqa foydalanuvchi tomonidan o'zgartirilgan. Yangilang.")


def invalid_transition(frm, to):
    return ApiError(422, "INVALID_TRANSITION", "Bu holatdan tanlangan holatga o'tib bo'lmaydi.", frm=frm, to=to)


def validation(code, message, **extra):
    return ApiError(422, code, message, **extra)
