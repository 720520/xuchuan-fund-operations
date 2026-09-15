import { useEffect, useState, type ReactNode } from "react";
import { Mail, Paperclip } from "lucide-react";
import { useResource, mailCategoryLabel, timestamp, type MailItem, type Mailbox } from "./api";
import { Button } from "./components/ui/button";

type MailPage = { items: MailItem[]; total: number; offset: number; limit: number };
export function MailWorkspace({ base, boxes, boxesError, revision, canWrite, target, renderDetail, onAction, onClassify }: {
  base: string; boxes: Mailbox[]; boxesError?: string; revision: number; canWrite: boolean;
  target?: { itemId: string; request: number } | null;
  renderDetail: (item: MailItem) => ReactNode;
  onAction: (item: MailItem) => void; onClassify: (item: MailItem) => void;
}) {
  const [mailbox, setMailbox] = useState("");
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState("");
  const [targetItem, setTargetItem] = useState("");
  useEffect(() => {
    if (!target?.itemId) return;
    setMailbox("");
    setFilter("all");
    setSearch("");
    setOffset(0);
    setSelected(target.itemId);
    setTargetItem(target.itemId);
  }, [target?.itemId, target?.request]);
  const params = new URLSearchParams({ paginated: "true", limit: "50", offset: String(offset), view: filter, q: search });
  if (mailbox) params.set("mailbox_id", mailbox);
  if (targetItem) params.set("item_id", targetItem);
  const state = useResource<MailPage>(`${base}/mail-items?${params}`, revision);
  const items = state.data?.items || [];
  const item = items.find((entry) => entry.id === selected) || items[0];
  const currentBox = boxes.find((box) => box.id === mailbox);
  function chooseMailbox(id: string) { setTargetItem(""); setMailbox(id); setOffset(0); setSelected(""); setFilter("all"); setSearch(""); }
  return <section className="mail-workspace">
    <aside className="mail-account-nav" aria-label="选择接收邮箱">
      <h2>邮箱</h2>
      {boxesError && <p role="alert">{boxesError}</p>}
      <button className={!mailbox ? "current" : ""} aria-pressed={!mailbox} onClick={() => chooseMailbox("")}><Mail size={16} /><span><strong>全部邮箱</strong><small>全部已接收邮件</small></span></button>
      {boxes.map((box) => <button key={box.id} className={mailbox === box.id ? "current" : ""} aria-pressed={mailbox === box.id} onClick={() => chooseMailbox(box.id)}>
        <Mail size={16} /><span><strong>{box.label}</strong><small>{box.username || "已登记邮箱"}</small><small>{box.error ? "同步异常" : box.enabled ? "已启用" : "已停用"}</small></span>
      </button>)}
      {!boxes.length && !boxesError && <p>尚未接入邮箱，请在组织与权限中配置。</p>}
      <p className="mail-readonly-note">只读接收 · 原件留存</p>
    </aside>
    <section className="mail-message-list" aria-label="邮件列表">
      <header><h2>{currentBox?.label || "全部邮箱"}</h2><small>{state.data ? `${state.data.total} 封邮件` : "正在加载…"}</small>
        <input aria-label="搜索邮件" placeholder="搜索主题、发件人或产品" value={search} onChange={(e) => { setTargetItem(""); setSearch(e.target.value); setOffset(0); setSelected(""); }} />
        <select aria-label="邮件处理状态" value={filter} onChange={(e) => { setTargetItem(""); setFilter(e.target.value); setOffset(0); setSelected(""); }}>
          <option value="all">全部邮件</option><option value="action">待处理</option><option value="receipt">接收记录</option><option value="pending">待分类</option><option value="completed">已完成</option>
        </select>
      </header>
      {state.error && <p className="mail-list-note" role="alert">{state.error}</p>}
      <div className="mail-message-rows">
        {items.map((entry) => <button key={entry.id} className={`mail-message-row ${entry.id === item?.id ? "current" : ""}`} aria-pressed={entry.id === item?.id} onClick={() => setSelected(entry.id)}>
          <span className="mail-row-sender">{entry.sender || "发件人未提供"}</span>
          <strong>{entry.title || "（无主题）"}</strong>
          <span className="mail-row-excerpt">{entry.excerpt || "暂无正文摘要"}</span>
          <span className="mail-row-foot"><time>{timestamp(entry.created_at)}</time>{entry.attachment_count > 0 && <span><Paperclip size={12} />{entry.attachment_count}</span>}</span>
          <small>{mailCategoryLabel(entry.category)}{entry.action?.status === "open" ? " · 待处理" : ""}</small>
        </button>)}
        {!items.length && !state.error && <p className="mail-list-note">{state.loading ? "正在读取邮件…" : "当前范围暂无邮件"}</p>}
      </div>
      <footer className="mail-list-pagination">
        <Button variant="ghost" disabled={offset === 0 || state.loading} onClick={() => { setTargetItem(""); setOffset(Math.max(0, offset - 50)); setSelected(""); }}>上一页</Button>
        <span>{Math.floor(offset / 50) + 1} / {Math.max(1, Math.ceil((state.data?.total || 0) / 50))}</span>
        <Button variant="ghost" disabled={state.loading || !state.data || offset + 50 >= state.data.total} onClick={() => { setTargetItem(""); setOffset(offset + 50); setSelected(""); }}>下一页</Button>
      </footer>
    </section>
    <article className="mail-reading-pane" aria-label="邮件正文与附件">
      {currentBox && <div className="mail-current-source">{currentBox.label} · 最近同步 {timestamp(currentBox.last_sync)}{currentBox.error && <p role="alert">{currentBox.error}</p>}</div>}
      {item ? <>
        {canWrite && (item.action?.status === "open" || item.status === "pending") && <div className="mail-reading-actions">
          {item.action?.status === "open" && <><span>{item.action.suggested_action}</span><Button variant="outline" onClick={() => onAction(item)}>处理待办</Button></>}
          {item.status === "pending" && <Button variant="outline" onClick={() => onClassify(item)}>确认分类</Button>}
        </div>}
        {renderDetail(item)}
      </> : <p className="mail-list-note">{state.loading ? "正在读取…" : "选择邮件后在此阅读正文和附件"}</p>}
    </article>
  </section>;
}
