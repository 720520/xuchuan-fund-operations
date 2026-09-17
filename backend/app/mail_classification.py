"""Deterministic mail classification and routing with the original as evidence."""

import hashlib
import re
from dataclasses import dataclass
from email.message import Message
from html import escape
from html.parser import HTMLParser

from sqlalchemy import select

from .db import now
from .models import (
    Document,
    MailAction,
    MailItem,
    MailItemProduct,
    ParseJob,
    Product,
)


# Structured data files enter the NAV parser.  A PDF is a formal original for
# review/archiving even when it arrives in the same valuation email.
SUPPORTED_NAV_ATTACHMENTS = (".xlsx", ".xls", ".csv", ".xlsm")


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in {"style", "script", "head", "template"}:
            self.hidden_depth += 1
        elif not self.hidden_depth and tag.lower() in {
            "br",
            "div",
            "p",
            "li",
            "tr",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
        }:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag.lower() in {"style", "script", "head", "template"} and self.hidden_depth:
            self.hidden_depth -= 1
        elif not self.hidden_depth and tag.lower() in {
            "div",
            "p",
            "li",
            "tr",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
        }:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden_depth:
            self.parts.append(data)


_EMAIL_HTML_TAGS = frozenset(
    {
        "a",
        "b",
        "blockquote",
        "br",
        "center",
        "code",
        "col",
        "colgroup",
        "div",
        "em",
        "font",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "hr",
        "i",
        "img",
        "li",
        "ol",
        "p",
        "pre",
        "s",
        "small",
        "span",
        "strong",
        "sub",
        "sup",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
        "u",
        "ul",
    }
)
_EMAIL_HTML_VOID_TAGS = frozenset({"br", "col", "hr", "img"})
_EMAIL_HTML_DROP_CONTENT = frozenset(
    {
        "applet",
        "audio",
        "button",
        "form",
        "frame",
        "frameset",
        "head",
        "iframe",
        "math",
        "object",
        "option",
        "script",
        "select",
        "style",
        "svg",
        "template",
        "textarea",
        "video",
    }
)
_EMAIL_HTML_IGNORED_VOID = frozenset({"base", "embed", "input", "link", "meta"})
_EMAIL_CSS_PROPERTIES = frozenset(
    {
        "align-content",
        "align-items",
        "align-self",
        "background",
        "background-color",
        "border",
        "border-bottom",
        "border-bottom-color",
        "border-bottom-style",
        "border-bottom-width",
        "border-collapse",
        "border-color",
        "border-left",
        "border-left-color",
        "border-left-style",
        "border-left-width",
        "border-radius",
        "border-right",
        "border-right-color",
        "border-right-style",
        "border-right-width",
        "border-spacing",
        "border-style",
        "border-top",
        "border-top-color",
        "border-top-style",
        "border-top-width",
        "border-width",
        "box-sizing",
        "color",
        "display",
        "flex",
        "flex-basis",
        "flex-direction",
        "flex-grow",
        "flex-shrink",
        "flex-wrap",
        "font-family",
        "font-size",
        "font-style",
        "font-variant",
        "font-weight",
        "height",
        "justify-content",
        "letter-spacing",
        "line-height",
        "margin",
        "margin-bottom",
        "margin-left",
        "margin-right",
        "margin-top",
        "max-height",
        "max-width",
        "min-height",
        "min-width",
        "padding",
        "padding-bottom",
        "padding-left",
        "padding-right",
        "padding-top",
        "table-layout",
        "text-align",
        "text-decoration",
        "text-indent",
        "text-transform",
        "vertical-align",
        "white-space",
        "width",
        "word-break",
        "word-spacing",
        "word-wrap",
    }
)


def _safe_email_style(value):
    declarations = []
    for declaration in str(value).split(";"):
        if ":" not in declaration:
            continue
        name, raw_value = declaration.split(":", 1)
        name = name.strip().lower()
        raw_value = raw_value.strip()
        unsafe = raw_value.lower()
        if (
            name not in _EMAIL_CSS_PROPERTIES
            or not raw_value
            or len(raw_value) > 300
            or any(
                marker in unsafe
                for marker in (
                    "url(",
                    "expression",
                    "javascript:",
                    "@import",
                    "behavior:",
                    "-moz-binding",
                )
            )
        ):
            continue
        declarations.append(f"{name}: {raw_value}")
    return "; ".join(declarations)[:4000]


def _safe_email_css(value):
    """Keep ordinary email presentation rules while removing network-capable CSS."""
    value = re.sub(r"/\*.*?\*/", "", str(value), flags=re.DOTALL)
    rules = []
    for selector, declarations in re.findall(r"([^{}]+)\{([^{}]*)\}", value):
        selector = selector.strip()
        if (
            not selector
            or selector.startswith("@")
            or len(selector) > 300
            or not re.fullmatch(r"[a-zA-Z0-9_#.\-\s,:>+~*\[\]='\"()]+", selector)
        ):
            continue
        safe_declarations = _safe_email_style(declarations)
        if safe_declarations:
            rules.append(f"{selector}{{{safe_declarations}}}")
    return "".join(rules)[:20000]


class _EmailHTMLSanitizer(HTMLParser):
    """Small allow-list sanitizer for displaying archived email in a sandboxed iframe."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden_depth = 0

    def _attributes(self, tag, attrs):
        result = []
        for raw_name, raw_value in attrs:
            name = raw_name.lower()
            value = str(raw_value or "").strip()
            if name == "style":
                value = _safe_email_style(value)
            elif name in {"align", "valign"}:
                value = value.lower() if value.lower() in {
                    "left",
                    "center",
                    "right",
                    "justify",
                    "top",
                    "middle",
                    "bottom",
                    "baseline",
                } else ""
            elif name in {"width", "height"}:
                value = value if re.fullmatch(r"\d{1,4}(?:px|%)?", value) else ""
            elif name in {"cellpadding", "cellspacing", "border", "colspan", "rowspan"}:
                value = value if re.fullmatch(r"\d{1,3}", value) else ""
            elif name in {"bgcolor", "color"}:
                value = value if re.fullmatch(r"#[0-9a-fA-F]{3,8}|[a-zA-Z]{1,24}", value) else ""
            elif name == "dir":
                value = value.lower() if value.lower() in {"ltr", "rtl", "auto"} else ""
            elif name == "alt" and tag == "img":
                value = value[:500]
            elif name == "src" and tag == "img":
                value = value if re.match(
                    r"^data:image/(?:png|gif|jpe?g|webp);base64,[a-zA-Z0-9+/=\s]+$",
                    value,
                ) else ""
            elif name == "title":
                value = value[:500]
            elif name == "class":
                value = value if re.fullmatch(r"[a-zA-Z0-9 _-]{1,500}", value) else ""
            elif name == "id":
                value = value if re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_:-]{0,100}", value) else ""
            else:
                value = ""
            if value:
                result.append(f' {name}="{escape(value, quote=True)}"')
        return "".join(result)

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if self.hidden_depth:
            if tag in _EMAIL_HTML_DROP_CONTENT:
                self.hidden_depth += 1
            return
        if tag in _EMAIL_HTML_IGNORED_VOID:
            return
        if tag in _EMAIL_HTML_DROP_CONTENT:
            self.hidden_depth = 1
            return
        if tag in _EMAIL_HTML_TAGS:
            self.parts.append(f"<{tag}{self._attributes(tag, attrs)}>")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self.hidden_depth:
            if tag in _EMAIL_HTML_DROP_CONTENT:
                self.hidden_depth -= 1
            return
        if tag in _EMAIL_HTML_TAGS and tag not in _EMAIL_HTML_VOID_TAGS:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data):
        if not self.hidden_depth:
            self.parts.append(escape(data))


def safe_message_html(message: Message):
    """Return inactive, self-contained HTML when the message has an HTML alternative."""
    candidates = []
    for part in message.walk():
        if (
            part.is_multipart()
            or part.get_content_disposition() == "attachment"
            or part.get_content_type() != "text/html"
        ):
            continue
        try:
            candidates.append(str(part.get_content()))
        except Exception:
            continue
    if not candidates:
        return None
    source = max(candidates, key=len)
    safe_css = "".join(
        _safe_email_css(block)
        for block in re.findall(r"<style[^>]*>(.*?)</style\s*>", source, flags=re.I | re.S)
    )[:20000]
    sanitizer = _EmailHTMLSanitizer()
    try:
        sanitizer.feed(source)
        sanitizer.close()
    except Exception:
        return None
    body = "".join(sanitizer.parts).strip()
    if not body:
        return None
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; "
        "img-src data:; style-src 'unsafe-inline'; font-src data:; media-src 'none'; "
        "frame-src 'none'; form-action 'none'; base-uri 'none'\">"
        "<style>html{color-scheme:light}body{margin:0;background:#fffefa;"
        "color:#30322d;font-family:Arial,'Microsoft YaHei',sans-serif;line-height:1.6;"
        "overflow-wrap:anywhere}table{max-width:100%}img{max-width:100%;height:auto}"
        f"{safe_css}"
        "html,body{width:100%!important;height:100%!important;overflow:hidden!important}"
        "#xuchuan-mail-scroll{box-sizing:border-box;width:100%;height:100vh;"
        "max-width:none!important;margin:0!important;padding:24px;overflow:auto!important;"
        "scrollbar-gutter:stable;scrollbar-color:#a8aa9f #eeeee8}"
        "#xuchuan-mail-scroll::-webkit-scrollbar{width:12px;height:12px}"
        "#xuchuan-mail-scroll::-webkit-scrollbar-track{background:#eeeee8}"
        "#xuchuan-mail-scroll::-webkit-scrollbar-thumb{background:#a8aa9f;border:3px solid #eeeee8;"
        "border-radius:8px}"
        "</style>"
        f"</head><body><div id=\"xuchuan-mail-scroll\">{body}</div></body></html>"
    )


@dataclass(frozen=True)
class Classification:
    category: str
    handling_mode: str
    priority: str
    confidence: int
    suggested_action: str | None = None


def _message_text(message: Message):
    parts = []
    for part in message.walk():
        if part.is_multipart() or part.get_content_disposition() == "attachment":
            continue
        if part.get_content_type() not in {"text/plain", "text/html"}:
            continue
        try:
            content = part.get_content()
        except Exception:  # malformed external mail is still archived
            continue
        if part.get_content_type() == "text/html":
            parser = _TextExtractor()
            try:
                parser.feed(str(content))
                content = " ".join(parser.parts)
            except Exception:
                content = ""
        parts.append(str(content))
    return re.sub(r"\s+", " ", " ".join(parts)).strip()[:20000]


def full_message_text(message: Message):
    """Return the complete visible body as inert text, preferring the HTML alternative."""
    plain_parts = []
    html_parts = []
    for part in message.walk():
        if part.is_multipart() or part.get_content_disposition() == "attachment":
            continue
        content_type = part.get_content_type()
        if content_type not in {"text/plain", "text/html"}:
            continue
        try:
            content = str(part.get_content())
        except Exception:  # malformed external mail remains downloadable as an original
            continue
        if content_type == "text/html":
            parser = _TextExtractor()
            try:
                parser.feed(content)
                content = "".join(parser.parts)
            except Exception:
                continue
            html_parts.append(content)
        else:
            plain_parts.append(content)
    selected = html_parts or plain_parts
    text = "\n\n".join(part for part in selected if part.strip())
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return re.sub(r"\n{4,}", "\n\n\n", text).strip()


def _contains(text, phrases):
    return any(phrase in text for phrase in phrases)


def classify(message: Message, folder=""):
    subject = str(message.get("Subject", ""))
    body = _message_text(message)
    filenames = " ".join(
        str(part.get_filename() or "") for part in message.walk() if part.get_filename()
    )
    subject_and_files = f"{subject} {filenames}".lower()
    all_text = f"{subject} {body} {filenames}".lower()
    folder_text = str(folder).strip().lower()
    action_phrases = (
        "待办",
        "待处理",
        "请确认",
        "请提供",
        "请提交",
        "请回复",
        "请核查",
        "欠件",
        "补充材料",
        "及时提交",
    )

    if _contains(
        all_text,
        ("新设备登录", "异常登录", "密码变更", "密码修改", "凭据变更", "授权码变更"),
    ):
        return Classification("security", "task", "high", 98, "核查账号安全提醒")
    if _contains(
        all_text, ("投资监督", "违反", "违规", "超限", "交割月风险", "风险提示")
    ):
        return Classification("risk_monitoring", "task", "high", 96, "核查风险或投资监督事项")
    if _contains(subject_and_files, ("投资人份额", "投资者份额", "持仓份额表")):
        return Classification("investor_redemption", "receipt", "normal", 98)
    if _contains(subject_and_files, ("估值表", "估值文件", "净值", "单位净值")):
        return Classification("nav_valuation", "receipt", "normal", 96)
    if _contains(folder_text, ("基金估值", "净值")):
        return Classification("nav_valuation", "receipt", "normal", 85)
    if _contains(subject_and_files, ("期货结算单", "结算单")):
        return Classification("futures_settlement", "receipt", "normal", 95)
    if _contains(folder_text, ("期货结算", "结算单")):
        return Classification("futures_settlement", "receipt", "normal", 85)
    if _contains(all_text, ("申购", "赎回", "投资者", "份额确认")):
        if _contains(all_text, action_phrases):
            return Classification(
                "investor_redemption", "task", "high", 92, "处理申赎或投资者事项"
            )
        return Classification("investor_redemption", "receipt", "normal", 86)
    if _contains(all_text, ("合同", "用印", "盖章", "协议")):
        if _contains(all_text, action_phrases):
            return Classification(
                "contract_seal", "task", "normal", 91, "处理合同或用印事项"
            )
        return Classification("contract_seal", "receipt", "normal", 84)
    if _contains(subject_and_files, ("对账", "数据包", "账户数据")):
        return Classification("reconciliation_data", "receipt", "normal", 91)
    if _contains(all_text, action_phrases):
        return Classification("action_required", "task", "high", 90, "按邮件要求核查并处理")
    if _contains(subject_and_files, ("已完成", "发送成功", "接收成功", "办理完成")):
        return Classification("completion_receipt", "receipt", "low", 88)
    if _contains(subject_and_files, ("营销", "推广", "活动邀请")):
        return Classification("marketing", "archive", "low", 90)
    return Classification("unknown", "pending", "normal", 0)


def _first_date(text):
    match = re.search(
        r"(?<!\d)(20\d{2})[年./-](0?[1-9]|1[0-2])[月./-](0?[1-9]|[12]\d|3[01])日?",
        text,
    )
    if match:
        return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    compact = re.search(
        r"(?<!\d)(20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?!\d)", text
    )
    if compact:
        return f"{compact.group(1)}-{compact.group(2)}-{compact.group(3)}"
    return None


def _due_at(text, business_date):
    if not business_date:
        return None
    times = re.findall(
        r"(?:截至|截止)\s*([01]?\d|2[0-3])[:：]([0-5]\d)(?!\d)", text
    )
    times += re.findall(
        r"(?<!\d)([01]?\d|2[0-3])[:：]([0-5]\d)\s*(?:前|之前)", text
    )
    if not times:
        return None
    hour, minute = times[-1]
    return f"{business_date}T{int(hour):02d}:{minute}:00+08:00"


def _safe_excerpt(message, classification):
    if classification.category == "security":
        return "安全提醒内容已限制展示，请打开原件核查。"
    return _message_text(message)[:500]


def _route_attachments(db, original, nav_candidate):
    attachments = list(
        db.scalars(select(Document).where(Document.parent_id == original.id))
    )
    for child in attachments:
        job = db.scalar(select(ParseJob).where(ParseJob.document_id == child.id))
        if not child.filename.lower().endswith(SUPPORTED_NAV_ATTACHMENTS):
            if job and job.status == "queued":
                job.status = "skipped"
                job.updated_at = now()
                job.result = {
                    "errors": [],
                    "reason": "该附件作为正式原件保留，不进入结构化数据解析",
                }
            continue
        duplicate_job = db.scalar(
            select(ParseJob)
            .join(Document, Document.id == ParseJob.document_id)
            .where(
                Document.manager_id == child.manager_id,
                Document.sha256 == child.sha256,
                Document.id != child.id,
                ParseJob.status.in_(
                    ["queued", "processing", "review", "completed", "manual_completed"]
                ),
            )
            .order_by(Document.received_at, Document.id)
            .limit(1)
        )
        if nav_candidate:
            if not job:
                if duplicate_job:
                    db.add(
                        ParseJob(
                            manager_id=original.manager_id,
                            document_id=child.id,
                            status="skipped",
                            result={
                                "reason": "附件内容与已归档材料完全相同，不重复解析",
                                "duplicate_document_id": duplicate_job.document_id,
                            },
                        )
                    )
                else:
                    db.add(ParseJob(manager_id=original.manager_id, document_id=child.id))
            elif job.status == "skipped" and not duplicate_job:
                job.status = "queued"
                job.updated_at = now()
                job.result = {}
        elif job and job.status == "queued":
            job.status = "skipped"
            job.updated_at = now()
            job.result = {
                "errors": [],
                "reason": "邮件分类结果不是净值或估值，未进入净值解析",
            }


def ensure_mail_item(db, original, message):
    existing = db.scalar(select(MailItem).where(MailItem.document_id == original.id))
    if existing:
        return existing
    result = classify(message, (original.metadata_json or {}).get("folder", ""))
    subject = str(message.get("Subject", "")).strip()[:500] or "（无主题邮件）"
    sender = str(message.get("From", "")).strip()[:500]
    body = _message_text(message)
    combined = f"{subject} {body}"
    business_date = _first_date(combined)
    item = MailItem(
        manager_id=original.manager_id,
        document_id=original.id,
        category=result.category,
        title=subject,
        sender=sender,
        business_date=business_date,
        handling_mode=result.handling_mode,
        priority=result.priority,
        classification_source="rule",
        confidence=result.confidence,
        status="pending" if result.handling_mode == "pending" else "received",
        excerpt=_safe_excerpt(message, result),
        created_at=original.received_at,
    )
    db.add(item)
    db.flush()
    search_text = f"{combined} " + " ".join(
        str(part.get_filename() or "") for part in message.walk() if part.get_filename()
    )
    for product in db.scalars(
        select(Product).where(Product.manager_id == original.manager_id)
    ):
        code_match = len(product.code) >= 4 and product.code.lower() in search_text.lower()
        if code_match or product.name in search_text:
            db.add(
                MailItemProduct(
                    manager_id=original.manager_id,
                    mail_item_id=item.id,
                    product_id=product.id,
                )
            )
    if result.suggested_action:
        db.add(
            MailAction(
                manager_id=original.manager_id,
                mail_item_id=item.id,
                suggested_action=result.suggested_action,
                due_at=_due_at(combined, business_date),
            )
        )
    _route_attachments(db, original, result.category == "nav_valuation")
    return item


def apply_manual_classification(db, item, category, handling_mode, suggested_action):
    original = db.get(Document, item.document_id)
    item.category = category
    item.handling_mode = handling_mode
    item.priority = "high" if category in {"risk_monitoring", "security"} else "normal"
    item.classification_source = "manual"
    item.confidence = 100
    item.status = "received"
    item.updated_at = now()
    item.revision += 1
    action = db.scalar(select(MailAction).where(MailAction.mail_item_id == item.id))
    if handling_mode == "task":
        description = suggested_action or "核查并处理邮件事项"
        if action:
            action.suggested_action = description
            action.status = "open"
            action.result = None
            action.updated_at = now()
            action.revision += 1
        else:
            db.add(
                MailAction(
                    manager_id=item.manager_id,
                    mail_item_id=item.id,
                    suggested_action=description,
                )
            )
    elif action and action.status == "open":
        action.status = "cancelled"
        action.result = {"reason": "人工分类后无需待办"}
        action.updated_at = now()
        action.revision += 1
    _route_attachments(
        db, original, category == "nav_valuation" and handling_mode != "archive"
    )
    return item


def classify_pending_mail(factory, settings, limit=500):
    """Backfill archived email before the worker considers queued parse jobs."""
    processed = 0
    with factory.begin() as db:
        pending = list(
            db.scalars(
                select(Document)
                .where(
                    Document.source == "email",
                    Document.media_type == "message/rfc822",
                    ~Document.id.in_(select(MailItem.document_id)),
                )
                .order_by(Document.received_at)
                .limit(limit)
            )
        )
        from email import policy
        from email.parser import BytesParser

        for original in pending:
            path = settings.storage / original.storage_key
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != original.sha256:
                continue
            message = BytesParser(policy=policy.default).parsebytes(raw)
            ensure_mail_item(db, original, message)
            processed += 1
    return processed
