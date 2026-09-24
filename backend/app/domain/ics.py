import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MAX_OCCURRENCES = 5000
MAX_EVENTS = 2000
MAX_STEPS = 200_000
MAX_BUSY = 5000
_WEEKDAYS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}
_DURATION_RE = re.compile(
    r"^(?P<sign>[+-])?P(?:(?P<w>\d+)W)?(?:(?P<d>\d+)D)?"
    r"(?:T(?:(?P<h>\d+)H)?(?:(?P<m>\d+)M)?(?:(?P<s>\d+)S)?)?$"
)

class IcsError(ValueError):
    pass

@dataclass(frozen=True)
class BusyEvent:
    starts_at: datetime
    ends_at: datetime
    title: str

@dataclass
class _Prop:
    value: str
    params: dict[str, str] = field(default_factory=dict)

@dataclass
class _VEvent:
    props: dict[str, list[_Prop]] = field(default_factory=dict)

    def first(self, name: str) -> _Prop | None:
        values = self.props.get(name)
        return values[0] if values else None

def _unfold(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        elif raw:
            lines.append(raw)
    return lines

def _split_prop(line: str) -> tuple[str, dict[str, str], str]:
    in_quotes = False
    colon = -1
    for i, ch in enumerate(line):
        if ch == '"':
            in_quotes = not in_quotes
        elif ch == ":" and not in_quotes:
            colon = i
            break
    if colon < 0:
        raise IcsError("bad_line")
    head, value = line[:colon], line[colon + 1 :]
    parts = head.split(";")
    params: dict[str, str] = {}
    for part in parts[1:]:
        if "=" in part:
            key, val = part.split("=", 1)
            params[key.upper()] = val.strip('"')
    return parts[0].upper(), params, value

def unescape_text(value: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(value):
        ch = value[i]
        if ch == "\\" and i + 1 < len(value):
            nxt = value[i + 1]
            out.append("\n" if nxt in "nN" else nxt)
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)

def escape_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )

def _zone(params: dict[str, str], default_tz: ZoneInfo) -> ZoneInfo:
    tzid = params.get("TZID")
    if not tzid:
        return default_tz
    try:
        return ZoneInfo(tzid.strip("/"))
    except (ZoneInfoNotFoundError, ValueError):
        return default_tz

def _parse_dt(prop: _Prop, default_tz: ZoneInfo) -> datetime | date:
    value = prop.value.strip()
    if prop.params.get("VALUE", "").upper() == "DATE" or re.fullmatch(r"\d{8}", value):
        try:
            return datetime.strptime(value[:8], "%Y%m%d").date()
        except ValueError as exc:
            raise IcsError("bad_date") from exc
    utc = value.endswith("Z")
    try:
        naive = datetime.strptime(value.rstrip("Z")[:15], "%Y%m%dT%H%M%S")
    except ValueError as exc:
        raise IcsError("bad_datetime") from exc
    if utc:
        return naive.replace(tzinfo=UTC)
    return naive.replace(tzinfo=_zone(prop.params, default_tz))

def _parse_duration(value: str) -> timedelta:
    m = _DURATION_RE.match(value.strip())
    if not m:
        raise IcsError("bad_duration")
    delta = timedelta(
        weeks=int(m["w"] or 0),
        days=int(m["d"] or 0),
        hours=int(m["h"] or 0),
        minutes=int(m["m"] or 0),
        seconds=int(m["s"] or 0),
    )
    return -delta if m["sign"] == "-" else delta

def _parse_events(text: str) -> list[_VEvent]:
    lines = _unfold(text)
    if not lines or lines[0].strip().upper() != "BEGIN:VCALENDAR":
        raise IcsError("not_calendar")
    events: list[_VEvent] = []
    current: _VEvent | None = None
    depth = 0
    for line in lines:
        upper = line.strip().upper()
        if upper == "BEGIN:VEVENT":
            current = _VEvent()
            depth = 0
            continue
        if current is None:
            continue
        if upper.startswith("BEGIN:"):
            depth += 1
            continue
        if upper.startswith("END:") and depth:
            depth -= 1
            continue
        if upper == "END:VEVENT":
            events.append(current)
            current = None
            continue
        if depth:
            continue
        name, params, value = _split_prop(line)
        current.props.setdefault(name, []).append(_Prop(value, params))
    return events

def _rrule(value: str) -> dict[str, str]:
    parts = {}
    for chunk in value.split(";"):
        if "=" in chunk:
            key, val = chunk.split("=", 1)
            parts[key.upper()] = val.upper()
    return parts

def _as_aware(value: datetime | date, tz: ZoneInfo) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.combine(value, time(23, 59, 59), tzinfo=tz)

class _Budget:

    def __init__(self, steps: int) -> None:
        self.left = steps

    def spend(self) -> None:
        self.left -= 1
        if self.left < 0:
            raise IcsError("too_complex")

def _small_int(value: str, default: int) -> int:
    value = value.strip()
    if not value:
        return default
    if not value.isdigit() or len(value) > 5:
        raise IcsError("bad_rrule")
    return int(value)

def _occurrence_starts(
    start: datetime,
    rule: dict[str, str],
    range_start: datetime,
    until_horizon: datetime,
    default_tz: ZoneInfo,
    budget: _Budget,
) -> list[datetime]:
    freq = rule.get("FREQ")
    if freq not in ("DAILY", "WEEKLY"):
        return [start]
    interval = max(1, _small_int(rule.get("INTERVAL", ""), 1))
    count = _small_int(rule["COUNT"], 0) if "COUNT" in rule else None
    until: datetime | None = None
    if "UNTIL" in rule:
        tz = start.tzinfo if isinstance(start.tzinfo, ZoneInfo) else default_tz
        until = _as_aware(_parse_dt(_Prop(rule["UNTIL"]), tz), tz)
    wall = start.time()

    def at_day(d: date) -> datetime:
        return datetime.combine(d, wall, tzinfo=start.tzinfo)

    out: list[datetime] = []
    start_day = start.date()
    skip_days = max(0, (range_start.date() - start_day).days - 1) if count is None else 0
    if freq == "DAILY":
        first = skip_days // interval
        days = (start_day + timedelta(days=i * interval) for i in range(first, 10**6))
    else:
        bydays = [
            _WEEKDAYS[d[-2:]] for d in rule.get("BYDAY", "").split(",") if d[-2:] in _WEEKDAYS
        ]
        if not bydays:
            bydays = [start_day.weekday()]
        bydays.sort()
        week0 = start_day - timedelta(days=start_day.weekday())
        first = skip_days // 7 // interval
        days = (
            week0 + timedelta(weeks=w * interval, days=wd)
            for w in range(first, 10**6)
            for wd in bydays
        )
    for d in days:
        budget.spend()
        occ = at_day(d)
        if occ < start:
            continue
        if until is not None and occ > until:
            break
        if occ > until_horizon:
            break
        out.append(occ)
        if count is not None and len(out) >= count:
            break
        if len(out) >= MAX_OCCURRENCES:
            break
    return out

def parse_busy(
    text: str, default_tz: ZoneInfo, range_start: datetime, range_end: datetime
) -> list[BusyEvent]:
    events = _parse_events(text)
    if len(events) > MAX_EVENTS:
        raise IcsError("too_many_events")
    budget = _Budget(MAX_STEPS)
    overridden: set[tuple[str, datetime]] = set()
    for ev in events:
        rid = ev.first("RECURRENCE-ID")
        uid = ev.first("UID")
        if rid and uid:
            value = _parse_dt(rid, default_tz)
            if isinstance(value, datetime):
                overridden.add((uid.value, value))

    busy: list[BusyEvent] = []
    for ev in events:
        status = ev.first("STATUS")
        if status and status.value.strip().upper() == "CANCELLED":
            continue
        dtstart = ev.first("DTSTART")
        if dtstart is None:
            continue
        start = _parse_dt(dtstart, default_tz)
        if not isinstance(start, datetime):
            continue
        dtend, duration = ev.first("DTEND"), ev.first("DURATION")
        if dtend is not None:
            end_value = _parse_dt(dtend, default_tz)
            if not isinstance(end_value, datetime):
                continue
            length = end_value - start
        elif duration is not None:
            length = _parse_duration(duration.value)
        else:
            length = timedelta(0)
        if length <= timedelta(0):
            continue
        summary = ev.first("SUMMARY")
        title = unescape_text(summary.value).strip() if summary else ""
        uid = ev.first("UID")

        excluded: set[datetime] = set()
        for exdate in ev.props.get("EXDATE", []):
            for chunk in exdate.value.split(","):
                value = _parse_dt(_Prop(chunk, exdate.params), default_tz)
                if isinstance(value, datetime):
                    excluded.add(value)

        rrule = ev.first("RRULE")
        is_override = ev.first("RECURRENCE-ID") is not None
        starts = (
            _occurrence_starts(
                start, _rrule(rrule.value), range_start, range_end, default_tz, budget
            )
            if rrule and not is_override
            else [start]
        )
        for occ in starts:
            if occ in excluded:
                continue
            if uid and not is_override and (uid.value, occ) in overridden:
                continue
            occ_end = occ + length
            if occ_end <= range_start or occ >= range_end:
                continue
            busy.append(BusyEvent(occ, occ_end, title))
            if len(busy) > MAX_BUSY:
                raise IcsError("too_many_events")
    busy.sort(key=lambda e: (e.starts_at, e.ends_at))
    return busy

def _fmt_utc(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")

def _fold(line: str) -> str:
    data = line.encode()
    if len(data) <= 75:
        return line
    chunks: list[str] = []
    current = b""
    limit = 75
    for ch in line:
        enc = ch.encode()
        if len(current) + len(enc) > limit:
            chunks.append(current.decode())
            current = b""
            limit = 74
        current += enc
    chunks.append(current.decode())
    return "\r\n ".join(chunks)

def build_event(
    *,
    uid: str,
    starts_at: datetime,
    ends_at: datetime,
    summary: str,
    location: str,
    description: str,
    stamp: datetime,
) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Vremya s polzoy//RU",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{_fmt_utc(stamp)}",
        f"DTSTART:{_fmt_utc(starts_at)}",
        f"DTEND:{_fmt_utc(ends_at)}",
        f"SUMMARY:{escape_text(summary)}",
        f"LOCATION:{escape_text(location)}",
        f"DESCRIPTION:{escape_text(description)}",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
