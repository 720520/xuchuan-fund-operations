import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";
import { timestamp, useResource } from "./api";
import { Button } from "./components/ui/button";

type CalendarDay = {
  date: string;
  weekday: number;
  trading_day: boolean;
  holiday_name: string | null;
  makeup_workday: boolean;
};

type CalendarPayload = {
  month: string;
  refresh: {
    status: "bundled" | "verified" | "review" | "unavailable";
    checked_at?: string | null;
    error?: string;
  };
  days: CalendarDay[];
};

function localDate(partNames: ("year" | "month" | "day")[]) {
  const parts = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    ...(partNames.includes("day") ? { day: "2-digit" } : {}),
  }).formatToParts(new Date());
  const value = (type: string) => parts.find((part) => part.type === type)?.value || "";
  return partNames
    .map((name) => (name === "year" ? value(name) : value(name).padStart(2, "0")))
    .join("-");
}

const monthNow = () => localDate(["year", "month"]);
const dayNow = () => localDate(["year", "month", "day"]);

function shiftMonth(value: string, delta: number) {
  const [year, month] = value.split("-").map(Number);
  const shifted = new Date(Date.UTC(year, month - 1 + delta, 1));
  return `${shifted.getUTCFullYear()}-${String(shifted.getUTCMonth() + 1).padStart(2, "0")}`;
}

export function OperationCalendar({ managerId, revision }: { managerId: string; revision: number }) {
  const [month, setMonth] = useState(monthNow());
  const state = useResource<CalendarPayload>(
    `/managers/${managerId}/calendar?month=${month}`,
    revision,
  );
  const data = state.data;
  const firstWeekday = data?.days[0]?.weekday ?? 0;
  const refreshText =
    data?.refresh.status === "verified"
      ? `已核验 ${timestamp(data.refresh.checked_at)}`
      : data?.refresh.status === "review"
        ? "官方页面有变化，待复核"
        : data?.refresh.status === "unavailable"
          ? "官方页面暂时无法核验"
          : "每 30 天核验官方安排";

  return (
    <section className="panel operation-calendar">
      <div className="calendar-heading">
        <div className="calendar-title">
          <CalendarDays size={17} />
          <h2>运营日历</h2>
        </div>
        <div className="calendar-controls">
          <Button variant="ghost" size="icon" aria-label="上个月" onClick={() => setMonth(shiftMonth(month, -1))}>
            <ChevronLeft size={15} />
          </Button>
          <button className="calendar-month" onClick={() => setMonth(monthNow())} title="回到本月">
            {Number(month.slice(0, 4))}年{Number(month.slice(5))}月
          </button>
          <Button variant="ghost" size="icon" aria-label="下个月" onClick={() => setMonth(shiftMonth(month, 1))}>
            <ChevronRight size={15} />
          </Button>
        </div>
      </div>
      {state.error ? (
        <p role="alert" className="calendar-error">{state.error}</p>
      ) : (
        <div className="calendar-main">
          <div className="calendar-weekdays">
            {['一', '二', '三', '四', '五', '六', '日'].map((day) => <span key={day}>{day}</span>)}
          </div>
          <div className="calendar-grid">
            {Array.from({ length: firstWeekday }).map((_, index) => <span key={`blank-${index}`} className="calendar-blank" />)}
            {(data?.days || []).map((day) => (
              <article
                key={day.date}
                title={day.holiday_name || (day.makeup_workday ? "调休上班，证券市场休市" : day.trading_day ? "交易日" : "休市")}
                className={[
                  "calendar-day",
                  day.date === dayNow() ? "today" : "",
                  day.holiday_name ? "holiday" : "",
                  !day.trading_day ? "closed" : "",
                ].join(" ")}
              >
                <strong>{Number(day.date.slice(-2))}</strong>
                {day.holiday_name ? <span>{day.holiday_name}</span> : day.makeup_workday ? <span>调休</span> : null}
              </article>
            ))}
          </div>
          <div className="calendar-footer">
            <div className="calendar-legend">
              <span><i className="legend-trading" />交易日</span>
              <span><i className="legend-holiday" />节假日</span>
              <span><i className="legend-closed" />休市</span>
            </div>
            <small className={`calendar-refresh ${data?.refresh.status || "bundled"}`} title={data?.refresh.error}>{refreshText}</small>
          </div>
        </div>
      )}
    </section>
  );
}
