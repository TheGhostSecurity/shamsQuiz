from rest_framework.views import exception_handler as drf_exception_handler
from rest_framework import status


def api_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    detail = response.data
    message = ''
    fields = {}

    if isinstance(detail, dict):
        if 'detail' in detail:
            message = str(detail['detail'])
        else:
            for key, value in detail.items():
                if isinstance(value, (list, tuple)) and value:
                    fields[key] = [str(v) for v in value]
                else:
                    fields[key] = [str(value)]
    elif isinstance(detail, (list, tuple)) and detail:
        message = str(detail[0])
    else:
        message = str(detail)

    return bad_request(message or 'Something went wrong. Please try again.', fields, response.status_code)


def bad_request(message, fields=None, code=status.HTTP_400_BAD_REQUEST):
    from rest_framework.response import Response

    fields = fields or {}
    if len(fields) == 1:
        key = next(iter(fields))
        detail = fields[key][0] if fields[key] else ''
        if detail:
            message = f"{key}: {detail}"

    return Response(
        {'ok': False, 'error': message, 'fields': fields},
        status=code,
    )
