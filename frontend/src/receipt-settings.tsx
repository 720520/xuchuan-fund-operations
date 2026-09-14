import { useState } from "react";
import { ActionForm, Field, val } from "./forms";
import { Input } from "./components/ui/input";
import { put, timestamp } from "./api";

export type ReceiptPolicy = {
  enabled: boolean;
  start_date: string;
  followup_time: string;
  last_scheduled_date?: string | null;
  last_checked_at: string | null;
  error: string | null;
  calendar: string;
  calendar_error: string | null;
  calendar_sources: Record<string, string>;
  suggested_valuation_date: string | null;
};

export function ReceiptSettings({managerId, policy, done}: {
  managerId: string; policy: ReceiptPolicy; done: () => void;
}) {
  const [enabled, setEnabled] = useState(policy.enabled);
  return <section className="panel panel-spaced">
    <div className="panel-head"><div>
      <h2>净值自动应收</h2>
      <p>交易日接收前一交易日净值，15:00 截止；跨交易日未收到时提示核查托管补发。</p>
      <p>最近检查：{policy.last_checked_at ? timestamp(policy.last_checked_at) : "尚未执行"}</p>
      {policy.error && <p className="parse-error">{policy.error}</p>}
      {policy.calendar_error && <p className="parse-error">{policy.calendar_error}</p>}
    </div></div>
    <ActionForm label="保存应收设置" done={done} submit={f => put(`/managers/${managerId}/receipt-policy`, {
      enabled, start_date: val(f, "start_date"), followup_time: val(f, "followup_time"),
      calendar_confirmed: f.get("calendar_confirmed") === "on",
    })}>
      <label className="check-line"><input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} />启用自动应收检查</label>
      <div className="field-pair">
        <Field label="应收检查起始日" hint="按收到材料的日期计算；首次启用不追补之前缺件">
          <Input name="start_date" type="date" required defaultValue={policy.start_date} readOnly={policy.last_scheduled_date !== undefined} />
        </Field>
        <Field label="下一交易日跟进时间" hint="初始建议 09:00，可按实际工作安排调整">
          <Input name="followup_time" type="time" required defaultValue={policy.followup_time} />
        </Field>
      </div>
      <p className="inline-note">北京时间；适用上交所交易日历，当前覆盖 2025–2026 年。周频按配置的估值星期，休市取此前交易日，下一交易日应收。已有应收记录保留原截止与跟进时间，修改仅用于后续新记录。</p>
      <p>{Object.entries(policy.calendar_sources).map(([year,url]) => <a key={year} href={url} target="_blank" rel="noreferrer" className="text-link">{year} 年日历依据　</a>)}</p>
      <label className="check-line"><input name="calendar_confirmed" type="checkbox" required />已核对本牌照应收产品适用此交易日历及跟进时间</label>
      <p className="inline-note">补发仍由运营在托管平台操作。停用暂停新检查，已产生的待办与原件保留。自动检查需后台处理服务运行。</p>
    </ActionForm>
  </section>;
}
