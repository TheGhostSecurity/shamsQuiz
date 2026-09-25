from django import template

from quiz.i18n import translate

register = template.Library()


@register.simple_tag(takes_context=True)
def t(context, text):
    return translate(str(text), context.get("lang", "en"))