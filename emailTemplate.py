"""HTML for every email the bot sends, in the Stamp design. The builders in emails.py describe an email
as plain content (a headline, rows of results, notes) and render() lays it out: a bold block of colour
heads each email (blue normally, sun yellow for a win, ink for an error) with your postcode on a
perforated stamp, over warm cream.

Email-client rules followed throughout: layout is nested tables (no flex or grid), every colour is
inline and repeated as a bgcolor attribute, widths are fixed at 600px for Outlook through MSO
conditionals, buttons are bulletproof (the cell carries the colour), and nothing depends on web
fonts, images or <style> support. The one <style> block only adds mobile padding where supported."""
from dataclasses import dataclass, field
import html

FONT = "'Helvetica Neue',Helvetica,Arial,sans-serif"
MONO = "'SF Mono',SFMono-Regular,Menlo,Consolas,'Liberation Mono','Courier New',monospace"


@dataclass
class Row:
    label: str
    meta: str = ''
    value: str = ''
    status: str = ''
    tone: str = 'neutral'  # win, warn, muted or neutral
    mono: bool = True      # the value is a postcode


@dataclass
class Rows:
    title: str
    rows: list


@dataclass
class Stats:
    items: list  # [(value, label)]


@dataclass
class Grid:
    """Every draw against every day of a week, as a glanceable matrix."""
    days: list  # [('Mon', '28')]
    rows: list  # [(draw label, [win, ok or none for each day])]


@dataclass
class Note:
    text: str
    tone: str = 'neutral'


@dataclass
class Code:
    title: str
    text: str


@dataclass
class Email:
    tone: str  # win, error, warn or neutral
    title: str
    intro: str
    preheader: str
    dateline: str = ''
    postcode: str = ''
    cta: tuple | None = None  # (label, url)
    blocks: list = field(default_factory=list)
    footer: str = ''


def _e(text):
    return html.escape(str(text), quote=True)


def _table(inner, style='', attrs=''):
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
            f'style="border-collapse:collapse;{style}"{attrs}>{inner}</table>')


def _button(label, url, bg, fg):
    """Bulletproof: the cell carries the colour, so Outlook still shows a button."""
    return (f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="border-collapse:separate;">'
            f'<tr><td align="center" bgcolor="{bg}" style="border-radius:12px;background-color:{bg};mso-padding-alt:14px 28px;">'
            f'<a href="{_e(url)}" target="_blank" style="display:inline-block;padding:14px 28px;border:1px solid {bg};'
            f'border-radius:12px;font-family:{FONT};font-size:15px;line-height:20px;font-weight:600;'
            f'color:{fg};text-decoration:none;text-align:center;">{_e(label)}</a></td></tr></table>')


def _pre(text, color):
    return (f'<div style="font-family:{MONO};font-size:12px;line-height:18px;color:{color};'
            f'white-space:pre-wrap;word-break:break-word;">{_e(text)}</div>')


_STYLE = """
body{margin:0!important;padding:0!important;width:100%!important;-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%;}
table,td{mso-table-lspace:0pt;mso-table-rspace:0pt;}
a{text-decoration:none;}
a[x-apple-data-detectors]{color:inherit!important;text-decoration:none!important;}
u + #body a{color:inherit;text-decoration:none;}
@media screen and (max-width:620px){
  .px{padding-left:22px!important;padding-right:22px!important;}
  .h1{font-size:28px!important;line-height:34px!important;}
  .stat{font-size:24px!important;line-height:30px!important;letter-spacing:-0.5px!important;}
}
"""


def _shell(email, canvas, body):
    """The document around the body: client resets, the hidden preheader and the 600px column."""
    filler = '&#8199;&#65279;&#847; ' * 40  # stops clients pulling body text into the inbox preview
    return f"""<!DOCTYPE html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="x-apple-disable-message-reformatting">
<meta name="format-detection" content="telephone=no,date=no,address=no,email=no,url=no">
<meta name="color-scheme" content="light">
<meta name="supported-color-schemes" content="light">
<title>{_e(email.title)}</title>
<!--[if mso]><noscript><xml><o:OfficeDocumentSettings><o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml></noscript><![endif]-->
<style>{_STYLE}</style>
</head>
<body id="body" style="margin:0;padding:0;background-color:{canvas};" bgcolor="{canvas}">
<div style="display:none;font-size:1px;line-height:1px;max-height:0;max-width:0;opacity:0;overflow:hidden;mso-hide:all;">{_e(email.preheader)}{filler}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="{canvas}" style="border-collapse:collapse;background-color:{canvas};">
<tr><td align="center" style="padding:32px 12px 40px;">
<!--[if mso]><table role="presentation" width="600" align="center" cellpadding="0" cellspacing="0" border="0"><tr><td><![endif]-->
<div style="max-width:600px;margin:0 auto;">
{body}
</div>
<!--[if mso]></td></tr></table><![endif]-->
</td></tr></table>
</body>
</html>"""


def render(email):
    ink, sub, faint, line, cream, paper, blue, sun = '#15163A', '#55566F', '#8E8C99', '#ECE5D6', '#F6F1E6', '#FFFDF8', '#2D3FE0', '#FFD43B'
    heroes = {  # (background, text, soft text, button bg, button text)
        'win': (sun, ink, '#4A4425', ink, sun),
        'neutral': (blue, paper, '#D5D9FF', paper, blue),
        'warn': (blue, paper, '#D5D9FF', paper, blue),
        'error': (ink, paper, '#B9BAD0', paper, ink),
    }
    bg, fg, soft, button_bg, button_fg = heroes[email.tone]
    nums = 'font-variant-numeric:tabular-nums;'

    def heading(title):
        return f'<div style="font-family:{FONT};font-size:15px;line-height:20px;font-weight:700;color:{blue};padding:34px 0 6px;">{_e(title)}</div>'

    def rows(block):
        out = ''
        for i, row in enumerate(block.rows):
            win = row.tone == 'win'
            top = '' if i == 0 else f'border-top:1px solid {line};'
            value = (f'<span style="display:inline-block;background-color:{sun};border-radius:6px;padding:2px 8px;">{_e(row.value)}</span>'
                     if win and row.mono else _e(row.value))
            out += (f'<tr><td valign="top" style="padding:13px 12px 13px 0;{top}">'
                    f'<div style="font-family:{FONT};font-size:16px;line-height:22px;font-weight:{700 if win else 500};color:{ink};">{_e(row.label)}</div>'
                    + (f'<div style="font-family:{FONT};font-size:13px;line-height:19px;color:{faint};{nums}">{_e(row.meta)}</div>' if row.meta else '') +
                    f'</td><td valign="top" align="right" style="padding:13px 0;{top}">'
                    f'<div style="font-family:{FONT};font-size:16px;line-height:22px;font-weight:{700 if win else 400};'
                    f'color:{faint if row.tone == "muted" else ink};{nums}white-space:nowrap;">{value}</div>'
                    + (f'<div style="font-family:{FONT};font-size:13px;line-height:19px;color:{"#A35A00" if row.tone == "warn" else faint};padding-top:2px;">{_e(row.status)}</div>' if row.status else '') +
                    '</td></tr>')
        return heading(block.title) + _table(out)

    def stats(block):
        cells = ''.join(
            f'<td width="{100 // len(block.items)}%" valign="top" bgcolor="{cream}" style="background-color:{cream};border-radius:14px;padding:16px 16px 14px;">'
            f'<div class="stat" style="font-family:{FONT};font-size:32px;line-height:36px;font-weight:700;letter-spacing:-1px;color:{ink};{nums}">{_e(value)}</div>'
            f'<div style="font-family:{FONT};font-size:13px;line-height:18px;color:{sub};">{_e(label)}</div></td>'
            + ('' if i == len(block.items) - 1 else '<td width="8" style="width:8px;font-size:1px;">&nbsp;</td>')
            for i, (value, label) in enumerate(block.items))
        return f'<div style="height:28px;line-height:28px;font-size:28px;">&nbsp;</div>{_table(f"<tr>{cells}</tr>", "border-collapse:separate;")}'

    def grid(block):
        def mark(tone):
            if tone == 'win':
                return (f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" align="center" style="border-collapse:separate;"><tr>'
                        f'<td width="22" height="22" align="center" valign="middle" bgcolor="{sun}" style="width:22px;height:22px;border-radius:11px;'
                        f'background-color:{sun};font-family:{FONT};font-size:12px;line-height:22px;font-weight:700;color:{ink};">&#10003;</td></tr></table>')
            if tone == 'ok':
                return f'<div style="font-size:16px;line-height:22px;color:#CFC7B6;">&#9679;</div>'
            return f'<div style="font-family:{FONT};font-size:13px;line-height:22px;font-weight:700;color:{blue};">?</div>'
        head = '<td></td>' + ''.join(
            f'<td align="center" width="9%" style="padding:0 0 8px;font-family:{FONT};font-size:12px;line-height:16px;color:{faint};">'
            f'{_e(weekday)}<br><span style="font-size:15px;line-height:20px;font-weight:700;color:{ink};">{_e(date)}</span></td>'
            for weekday, date in block.days)
        body = ''.join(
            f'<tr><td style="padding:7px 8px 7px 0;border-top:1px solid {line};font-family:{FONT};font-size:14px;line-height:20px;color:{ink};">{_e(name)}</td>'
            + ''.join(f'<td align="center" valign="middle" style="padding:7px 0;border-top:1px solid {line};">{mark(t)}</td>' for t in marks)
            + '</tr>'
            for name, marks in block.rows)
        legend = (f'<div style="font-family:{FONT};font-size:12px;line-height:18px;color:{sub};padding-top:10px;">'
                  f'<span style="color:#C9A400;">&#9679;</span> Won &nbsp;&nbsp; <span style="color:#CFC7B6;">&#9679;</span> No win &nbsp;&nbsp; '
                  f'<span style="color:{blue};font-weight:700;">?</span> Not checked</div>')
        return heading('Every draw') + _table(f'<tr>{head}</tr>{body}') + legend

    def note(block):
        warn = block.tone == 'warn'
        return ('<div style="height:20px;line-height:20px;font-size:20px;">&nbsp;</div>'
                + _table(f'<tr><td bgcolor="{sun if warn else cream}" style="background-color:{sun if warn else cream};border-radius:14px;padding:14px 18px;'
                         f'font-family:{FONT};font-size:14px;line-height:21px;font-weight:{600 if warn else 400};color:{ink if warn else sub};">{_e(block.text)}</td></tr>',
                         'border-collapse:separate;'))

    def code(block):
        return (f'<div style="font-family:{FONT};font-size:16px;line-height:22px;font-weight:700;color:{ink};padding:30px 0 10px;">{_e(block.title)}</div>'
                + (_table(f'<tr><td bgcolor="{cream}" style="background-color:{cream};border-radius:14px;padding:14px 16px;">{_pre(block.text, ink)}</td></tr>',
                          'border-collapse:separate;') if block.text else ''))

    render = {Rows: rows, Stats: stats, Grid: grid, Note: note, Code: code}
    blocks = ''.join(render[type(b)](b) for b in email.blocks)
    stamp = ''
    if email.postcode:
        outward, _, inward = email.postcode.partition(' ')
        stamp = (f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" align="right" style="border-collapse:separate;"><tr>'
                 f'<td bgcolor="{paper}" style="background-color:{paper};border:3px dotted {bg};outline:3px solid {paper};padding:8px 10px;">'
                 f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="border-collapse:separate;"><tr>'
                 f'<td align="center" style="border:1px solid {ink};padding:6px 9px;font-family:{FONT};color:{ink};">'
                 f'<div style="font-size:16px;line-height:18px;font-weight:700;letter-spacing:0.5px;">{_e(outward)}</div>'
                 f'<div style="font-size:16px;line-height:18px;font-weight:700;letter-spacing:0.5px;">{_e(inward)}</div>'
                 f'<div style="font-size:8px;line-height:12px;font-weight:700;letter-spacing:1px;color:{blue};padding-top:2px;">1ST</div>'
                 f'</td></tr></table></td></tr></table>')
    cta = (f'<div style="padding-top:28px;">{_button(email.cta[0] + "  →", email.cta[1], button_bg, button_fg)}</div>' if email.cta else '')
    body = f"""
{_table(f'''<tr><td bgcolor="{bg}" class="px" style="background-color:{bg};border-radius:22px 22px 0 0;padding:28px 36px 40px;">
  {_table(f"""<tr>
    <td valign="top" style="font-family:{FONT};font-size:15px;line-height:20px;font-weight:700;letter-spacing:-0.2px;color:{fg};">pick my postcode<div style="font-size:13px;line-height:18px;font-weight:400;letter-spacing:0;color:{soft};padding-top:2px;">{_e(email.dateline)}</div></td>
    <td valign="top" align="right" width="90">{stamp}</td>
  </tr>""")}
  <div class="h1" style="font-family:{FONT};font-size:46px;line-height:48px;font-weight:700;letter-spacing:-1.8px;color:{fg};padding-top:{18 if email.postcode else 36}px;">{_e(email.title)}</div>
  <div style="font-family:{FONT};font-size:17px;line-height:26px;color:{soft};padding-top:14px;">{_e(email.intro)}</div>
  {cta}
</td></tr>
<tr><td bgcolor="{paper}" class="px" style="background-color:{paper};border-radius:0 0 22px 22px;padding:8px 36px 40px;">{blocks}</td></tr>''', 'border-collapse:separate;')}
<div style="font-family:{FONT};font-size:12px;line-height:18px;color:{faint};padding:20px 8px 0;">{_e(email.footer)}</div>
"""
    return _shell(email, cream, body)
