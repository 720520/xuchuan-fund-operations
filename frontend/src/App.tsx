import { MailWorkspace } from "./mail-workspace";
import { ReceiptSettings, type ReceiptPolicy } from "./receipt-settings";
import { OperationCalendar } from "./operation-calendar";
import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  Activity,
  ArrowRight,
  Building2,
  ChartNoAxesCombined,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  ClipboardList,
  Download,
  FileText,
  FolderOpen,
  Layers3,
  LayoutDashboard,
  LockKeyhole,
  LogOut,
  Mail,
  Menu,
  Plus,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  Upload,
  X,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Button } from "./components/ui/button";
import { Input } from "./components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "./components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "./components/ui/table";
import {
  api,
  lifecycleLabel,
  post,
  put,
  useResource,
  number,
  sourceLabel,
  stageLabel,
  taskLabel,
  timestamp,
  type Audit,
  type Candidate,
  type Doc,
  type DocPage,
  type History,
  type Investor,
  type InvestorBankAccount,
  type InvestorShareEvent,
  type InvestorShareLedger,
  type ProductInvestorShareLedger,
  type MailDetail,
  type MailItem,
  type Mailbox,
  type Manager,
  type Me,
  type Member,
  type Product,
  type ProductFiling,
  type Task,
  mailCategoryLabel,
} from "./api";
import {
  ActionForm,
  Field,
  InvestorForm,
  InvestorBankAccountForm,
  InvestorPositionSnapshotForm,
  InvestorShareEventForm,
  LifecycleForm,
  MaterialForm,
  MemberForm,
  NavExportForm,
  NavForm,
  ProductForm,
  ScheduleForm,
  UploadForm,
  roles,
  val,
} from "./forms";

const navigation = [
  { id: "overview", label: "工作概览", icon: LayoutDashboard },
  { id: "products", label: "产品台账", icon: Layers3 },
  { id: "nav", label: "净值与估值", icon: ChartNoAxesCombined },
  { id: "mail", label: "邮件中心", icon: Mail },
  { id: "exceptions", label: "异常中心", icon: CircleAlert },
  { id: "upload", label: "资料中心", icon: FolderOpen },
  { id: "audit", label: "业务留痕", icon: ClipboardList },
  { id: "settings", label: "组织与权限", icon: Settings2 },
];

const materialCategories = [
  ["nav_valuation", "净值与估值"],
  ["contract", "合同与协议"],
  ["investor_qualification", "投资者准入与适当性"],
  ["subscription_redemption", "认申购与赎回材料"],
  ["filing", "产品备案与变更"],
  ["custody_account", "托管及账户材料"],
  ["periodic_report", "定期报告"],
  ["risk_compliance", "风险与合规通知"],
  ["operation_evidence", "运营处理凭证"],
  ["other", "其他资料"],
] as const;

function materialCategoryOf(document: Doc) {
  if (document.material_status !== "organized") return "pending";
  const explicit = document.category || document.metadata_json.material_category;
  if (explicit) return explicit;
  if (document.source === "lifecycle_material") return "operation_evidence";
  if (
    document.job?.status === "completed" &&
    (document.job.result.record_count || document.job.result.record_ids?.length)
  ) return "nav_valuation";
  return "pending";
}

function materialCategoryLabel(category: string) {
  if (category === "pending") return "待整理";
  return materialCategories.find(([value]) => value === category)?.[1] || "其他资料";
}

function materialProductIds(document: Doc) {
  return document.product_ids || document.products?.map((product) => product.id) || (document.product_id ? [document.product_id] : []);
}
const investorTypeLabels: Record<string, string> = {
  individual: "个人投资者",
  institution: "机构投资者",
  fund_product: "私募基金产品",
  asset_management: "资管计划",
  manager_co_investment: "管理人跟投",
  other: "其他",
};
const investorStatusLabels: Record<string, string> = {
  pending: "待核对",
  confirmed: "已核对",
  historical: "历史投资者",
};
const investorSourceLabels: Record<string, string> = {
  manual: "人工登记",
  directory_reference: "待整理目录索引",
  material: "已归档材料",
};
const suitabilityClassLabels: Record<string, string> = {
  ordinary: "普通投资者",
  professional: "专业投资者",
  unknown: "待确认",
};
const specificObjectStatusLabels: Record<string, string> = {
  unknown: "待确认",
  pending: "处理中",
  confirmed: "已确认",
  expired: "已失效",
  not_applicable: "不适用",
};
const qualifiedMaterialStatusLabels: Record<string, string> = {
  unknown: "待确认",
  missing: "缺失",
  valid: "有效",
  expired: "已到期",
  not_applicable: "不适用",
};
type InvestorChecklistItem = {
  key: string;
  label: string;
  patterns: string[];
  materialTypes?: string[];
  investorTypes?: Investor["investor_type"][];
  suitabilityClasses?: ("ordinary" | "professional" | "unknown")[];
};
const investorMaterialChecklist: InvestorChecklistItem[] = [
  { key: "commitment", label: "合格投资者承诺函", materialTypes: ["qualified_investor_commitment"], patterns: ["合格投资者承诺"] },
  { key: "risk", label: "风险测评问卷", materialTypes: ["risk_questionnaire"], patterns: ["风险测评", "风险评估", "评估问卷", "测评问卷"] },
  { key: "information", label: "投资者信息表", materialTypes: ["investor_information_form"], patterns: ["投资者信息表", "投资者基本信息表"] },
  { key: "identity", label: "个人身份证明", materialTypes: ["identity_front", "identity_back", "identity_document"], patterns: ["身份证", "身份证明", "证件照片"], investorTypes: ["individual"] },
  { key: "assets", label: "资产规模／收入证明", materialTypes: ["asset_proof"], patterns: ["资产规模", "资产证明", "收入证明", "金融资产"], investorTypes: ["individual"] },
  { key: "institution", label: "机构证明材料", materialTypes: ["institution_certificate"], patterns: ["营业执照", "许可证", "机构证明"], investorTypes: ["institution"] },
  { key: "representative", label: "法人及经办人证明", materialTypes: ["representative_identity", "authorization"], patterns: ["法人身份证", "法定代表人", "经办人", "授权委托"], investorTypes: ["institution", "fund_product", "asset_management"] },
  { key: "filing", label: "产品备案证明", materialTypes: ["product_filing_certificate"], patterns: ["备案函", "备案证明", "产品证明"], investorTypes: ["fund_product", "asset_management"] },
  { key: "tax", label: "税收身份声明", materialTypes: ["tax_declaration"], patterns: ["税收", "税务", "居民身份声明"] },
  { key: "professional", label: "专业投资者证明", materialTypes: ["professional_investor_proof"], patterns: ["专业投资者"], suitabilityClasses: ["professional", "unknown"] },
  { key: "specific", label: "特定对象确认材料", materialTypes: ["special_object_confirmation"], patterns: ["特定对象"] },
];
type InvestorDetailTab = "basic" | "suitability" | "accounts" | "general" | "business";
type Modal =
  | { kind: "product"; candidate?: Candidate; documentId?: string }
  | { kind: "filing" }
  | { kind: "nav"; task?: Task }
  | { kind: "nav-export"; productId?: string }
  | { kind: "upload"; productId?: string; investorId?: string }
  | { kind: "material"; document: Doc }
  | { kind: "investor"; investor?: Investor }
  | { kind: "bank-account"; investor: Investor; account?: InvestorBankAccount }
  | { kind: "share-event"; investor?: Investor; sourceMail?: MailItem }
  | { kind: "position-snapshot"; investor?: Investor; sourceMail?: MailItem }
  | { kind: "share-event-status"; event: InvestorShareEvent; status: "confirmed" | "archived" | "void" }
  | { kind: "schedule"; product: Product }
  | { kind: "lifecycle"; product: Product }
  | { kind: "member"; member?: Member }
  | { kind: "task"; task: Task }
  | { kind: "task-mail-disposition"; task: Task; disposition: "notification" | "duplicate" | "void" }
  | { kind: "mailbox"; mailbox?: Mailbox }
  | { kind: "mail-action"; item: MailItem }
  | { kind: "mail-classify"; item: MailItem }
  | { kind: "mail-detail"; item: MailItem }
  | { kind: "check" }
  | { kind: "share"; product: Product }
  | { kind: "password" }
  | { kind: "rules" };

type ShareWorkspaceTab = "positions" | "events" | "snapshots" | "sources";
type ShareInvestorSummary = ProductInvestorShareLedger["investors"][number]["investor"];
type ProductInvestorLedger = ProductInvestorShareLedger["investors"][number];
type ShareWorkspaceHolding = {
  key: string;
  title: string;
  subtitle: string;
  productId: string;
  position: InvestorShareLedger["positions"][number];
  ledger: InvestorShareLedger;
  investor?: ShareInvestorSummary;
  latestEvent?: InvestorShareEvent;
  latestSnapshot?: InvestorShareLedger["snapshots"][number];
};

const shareEventLabels: Record<InvestorShareEvent["event_type"], string> = {
  subscription: "申购",
  additional_subscription: "追加申购",
  redemption: "赎回",
  full_redemption: "全部赎回",
  cash_dividend: "现金分红",
  dividend_reinvestment: "红利再投资",
  transfer: "份额转让",
  adjustment: "份额调整",
};

const shareEventStatusLabels: Record<InvestorShareEvent["status"], string> = {
  pending: "待处理",
  confirmed: "已同步",
  archived: "仅归档",
  void: "已作废",
};

function shareEventDate(event?: InvestorShareEvent) {
  return event?.effective_date || event?.confirmation_date || event?.application_date || "";
}

function sameShare(
  shareId: string | null,
  candidate: { share_id: string | null },
) {
  return candidate.share_id === shareId;
}

function holdingCurrentUnits(holding: ShareWorkspaceHolding) {
  if (holding.position.current_units !== null) return holding.position.current_units;
  const snapshotDate = holding.position.snapshot_as_of_date || "";
  const eventDate = shareEventDate(holding.latestEvent);
  if (holding.position.latest_snapshot_units !== null && snapshotDate >= eventDate) {
    return holding.position.latest_snapshot_units;
  }
  return holding.latestEvent?.balance_after ?? holding.position.confirmed_units ?? holding.position.latest_snapshot_units;
}

function holdingHasDifference(holding: ShareWorkspaceHolding) {
  return Boolean(
    holding.position.difference &&
    Number(holding.position.difference) !== 0,
  );
}

function holdingDataDate(holding: ShareWorkspaceHolding) {
  if (holding.position.current_as_of_date) return holding.position.current_as_of_date;
  const snapshotDate = holding.position.snapshot_as_of_date || "";
  const eventDate = shareEventDate(holding.latestEvent);
  return snapshotDate >= eventDate ? snapshotDate : eventDate;
}

function InvestorShareWorkspace({
  revision,
  investors,
  products,
  canDownload,
  onOpenMail,
}: {
  revision: number;
  investors: Investor[];
  products: Product[];
  canDownload: boolean;
  onOpenMail: (id: string) => void;
}) {
  const [perspective, setPerspective] = useState<"investor" | "product">("investor");
  const [entityId, setEntityId] = useState("");
  const [holdingKey, setHoldingKey] = useState("");
  const [query, setQuery] = useState("");
  const [tab, setTab] = useState<ShareWorkspaceTab>("positions");
  const entities = perspective === "investor" ? investors : products;
  const selectedEntity = entities.find((entry) => entry.id === entityId) || entities[0];
  const selectedInvestor = perspective === "investor" ? selectedEntity as Investor | undefined : undefined;
  const selectedProduct = perspective === "product" ? selectedEntity as Product | undefined : undefined;
  const investorLedgerState = useResource<InvestorShareLedger>(
    selectedInvestor ? `/investors/${selectedInvestor.id}/share-events` : null,
    revision,
  );
  const productLedgerState = useResource<ProductInvestorShareLedger>(
    perspective === "product" && selectedProduct
      ? `/products/${selectedProduct.id}/investor-shares`
      : null,
    revision,
  );
  const productLedgers: ProductInvestorLedger[] = productLedgerState.data?.investors || [];

  const filteredEntities = entities.filter((entry) => {
    const haystack = perspective === "investor"
      ? `${(entry as Investor).display_name} ${investorTypeLabels[(entry as Investor).investor_type]}`
      : `${(entry as Product).name} ${(entry as Product).code}`;
    return haystack.toLowerCase().includes(query.trim().toLowerCase());
  });
  const activeLedger = investorLedgerState.data;
  const holdings: ShareWorkspaceHolding[] = perspective === "investor"
    ? (activeLedger?.positions || []).map((position) => {
        const latestEvent = activeLedger?.events.find(
          (event) => event.status !== "void" && event.product_id === position.product_id && sameShare(position.share_id, event),
        );
        const latestSnapshot = activeLedger?.snapshots.find(
          (snapshot) => snapshot.product_id === position.product_id && sameShare(position.share_id, snapshot),
        );
        return {
          key: `${position.product_id}:${position.share_id || "all"}`,
          title: position.product_name,
          subtitle: position.share_name || "总份额",
          productId: position.product_id,
          position,
          ledger: activeLedger!,
          latestEvent,
          latestSnapshot,
        };
      })
    : productLedgers.flatMap(({ investor, ledger }) =>
        ledger.positions.map((position) => ({
          key: `${investor.id}:${position.product_id}:${position.share_id || "all"}`,
          title: investor.display_name,
          subtitle: `${investorTypeLabels[investor.investor_type]} · ${position.share_name || "总份额"}`,
          productId: position.product_id,
          position,
          ledger,
          investor,
          latestEvent: ledger.events.find(
            (event) => event.status !== "void" && event.product_id === position.product_id && sameShare(position.share_id, event),
          ),
          latestSnapshot: ledger.snapshots.find(
            (snapshot) => snapshot.product_id === position.product_id && sameShare(position.share_id, snapshot),
          ),
        })),
      );
  const activeHolding = holdings.find((holding) => holding.key === holdingKey) || holdings[0];
  const activeHoldingKey = activeHolding?.key || "";
  const allEvents = perspective === "investor"
    ? (activeLedger?.events || []).map((event) => ({ event, investor: selectedInvestor }))
    : productLedgers.flatMap(({ investor, ledger }) => ledger.events.map((event) => ({ event, investor })));
  const allSnapshots = perspective === "investor"
    ? activeLedger?.snapshots || []
    : productLedgers.flatMap(({ ledger }) => ledger.snapshots);
  const sourceMailCount = new Set([
    ...allEvents.map(({ event }) => event.source_mail_item_id),
    ...allSnapshots.map((snapshot) => snapshot.source_mail_item_id),
  ].filter(Boolean)).size;
  const attentionCount = holdings.filter((holding) =>
    holdingHasDifference(holding) ||
    holding.latestEvent?.status === "pending",
  ).length;
  const loading = perspective === "investor" ? investorLedgerState.loading : productLedgerState.loading;
  const error = perspective === "investor" ? investorLedgerState.error : productLedgerState.error;

  function selectPerspective(next: "investor" | "product") {
    setPerspective(next);
    setEntityId("");
    setHoldingKey("");
    setQuery("");
    setTab("positions");
  }

  function renderSourceAction(event?: InvestorShareEvent, snapshot?: InvestorShareLedger["snapshots"][number]) {
    const mailId = event?.source_mail_item_id || snapshot?.source_mail_item_id;
    const documentId = event?.source_document_id || snapshot?.source_document_id;
    if (mailId) return <button className="text-link button-link" onClick={() => onOpenMail(mailId)}>查看原始邮件</button>;
    if (documentId && canDownload) return <a className="text-link" href={`/api/documents/${documentId}/download`}>下载来源附件</a>;
    return <span className="muted">来源已留痕</span>;
  }

  return (
    <section className="share-workspace panel">
      <div className="share-workspace-toolbar">
        <div className="material-direction" aria-label="份额查看方向">
          <button className={perspective === "investor" ? "current" : ""} onClick={() => selectPerspective("investor")}>按投资者</button>
          <button className={perspective === "product" ? "current" : ""} onClick={() => selectPerspective("product")}>按产品</button>
        </div>
        <div className="search-inline share-entity-search">
          <Search size={15} />
          <Input
            aria-label={perspective === "investor" ? "搜索投资者" : "搜索产品"}
            placeholder={perspective === "investor" ? "搜索投资者名称或类型" : "搜索产品名称或代码"}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
        <span className="share-auto-note"><i />邮件自动入账 · 仅异常需要处理</span>
      </div>
      <div className="share-workspace-grid">
        <aside className="share-entity-panel">
          <div className="material-entity-heading">
            <strong>{perspective === "investor" ? "投资者" : "产品"}</strong>
            <span>{filteredEntities.length} 个主体</span>
          </div>
          <div className="share-entity-list">
            {filteredEntities.map((entry) => {
              const investor = perspective === "investor" ? entry as Investor : undefined;
              const product = perspective === "product" ? entry as Product : undefined;
              const selected = entry.id === selectedEntity?.id;
              return (
                <button key={entry.id} className={selected ? "current" : ""} onClick={() => {
                  setEntityId(entry.id);
                  setHoldingKey("");
                }}>
                  <span className="material-entity-name"><i />{investor?.display_name || product?.name}</span>
                  <small>{investor ? `${investorTypeLabels[investor.investor_type]} · ${suitabilityClassLabels[investor.suitability_class || "unknown"]}` : `${product?.code || "产品代码待补"} · ${product?.shares.length || 0} 类份额`}</small>
                  <span className="material-entity-counts">
                    <small>{investor ? `${investor.product_ids.length} 个产品` : `${investors.filter((item) => item.product_ids.includes(entry.id)).length} 个投资者`}</small>
                    <small>{investor ? `${investor.material_count} 份资料` : `${product?.shares.length || 0} 类份额`}</small>
                  </span>
                </button>
              );
            })}
            {!filteredEntities.length && <p className="material-list-empty">没有符合条件的主体。</p>}
          </div>
        </aside>
        <div className="share-workspace-content">
          {selectedEntity ? (
            <>
              <header className="share-subject">
                <div>
                  <span>当前{perspective === "investor" ? "投资者" : "产品"}</span>
                  <h2>{selectedInvestor?.display_name || selectedProduct?.name}</h2>
                  <p>{selectedInvestor
                    ? `${investorTypeLabels[selectedInvestor.investor_type]} · ${suitabilityClassLabels[selectedInvestor.suitability_class || "unknown"]} · 最新份额以邮件记录为准`
                    : `${selectedProduct?.code || "产品代码待补"} · 按投资者查看持有份额及来源`}</p>
                </div>
                <div className="share-subject-stats">
                  <div><span>持仓项目</span><strong>{holdings.length}</strong></div>
                  <div><span>来源邮件</span><strong>{sourceMailCount}</strong></div>
                  <div className={attentionCount ? "attention" : ""}><span>差异／待处理</span><strong>{attentionCount}</strong></div>
                </div>
              </header>
              <nav className="share-tabs" aria-label="投资者份额分区">
                {([
                  ["positions", "当前份额", holdings.length],
                  ["events", "全部变动", allEvents.length],
                  ["snapshots", "托管快照", allSnapshots.length],
                  ["sources", "来源材料", sourceMailCount],
                ] as [ShareWorkspaceTab, string, number][]).map(([value, label, count]) => (
                  <button key={value} className={tab === value ? "current" : ""} onClick={() => setTab(value)}>{label}<small>{count}</small></button>
                ))}
              </nav>
              <ErrorNote error={error} />
              {tab === "positions" && (
                <div className="share-position-layout">
                  <section className="share-position-main">
                    <div className="share-section-heading"><div><strong>{perspective === "investor" ? "当前持有产品" : "当前投资者份额"}</strong><span>以邮件中的最新有效份额或托管快照为准</span></div></div>
                    {holdings.length ? (
                      <div className="share-position-list">
                        {holdings.map((holding) => {
                          const currentUnits = holdingCurrentUnits(holding);
                          const hasDifference = holdingHasDifference(holding);
                          const pending = holding.latestEvent?.status === "pending";
                          return (
                            <button key={holding.key} className={holding.key === activeHoldingKey ? "current" : ""} onClick={() => setHoldingKey(holding.key)}>
                              <span className="share-position-identity"><strong>{holding.title}</strong><small>{holding.subtitle} · 数据日 {holdingDataDate(holding) || "待补充"}</small></span>
                              <span className="share-position-number"><small>当前份额</small><strong>{currentUnits === null ? "待建立" : number(currentUnits)}</strong></span>
                              <span className="share-position-change"><small>最近变动</small><strong>{holding.latestEvent ? `${shareEventLabels[holding.latestEvent.event_type]} ${holding.latestEvent.units_delta === null ? "" : number(holding.latestEvent.units_delta)}` : "托管快照"}</strong></span>
                              <Status state={hasDifference || pending ? "open" : "completed"} text={hasDifference ? "快照差异" : pending ? "待处理" : "已同步"} />
                              <ChevronRight size={15} />
                            </button>
                          );
                        })}
                      </div>
                    ) : (
                      <Empty title={loading ? "正在读取份额…" : "尚无份额记录"} text="收到并识别投资者份额邮件后，将在这里自动形成当前持仓。" />
                    )}
                    {allEvents.length > 0 && (
                      <div className="share-recent-events">
                        <div className="share-section-heading"><div><strong>最近变动</strong><span>当前主体的最新业务记录</span></div></div>
                        <div className="share-compact-table">
                          <div className="share-compact-row heading"><span>业务日期</span><span>类型</span><span>{perspective === "investor" ? "产品" : "投资者"}</span><span>份额变动</span><span>来源</span></div>
                          {allEvents.slice(0, 5).map(({ event, investor }) => (
                            <div className="share-compact-row" key={event.id}><span>{shareEventDate(event) || "待补充"}</span><span>{shareEventLabels[event.event_type]}</span><span>{perspective === "investor" ? event.product_name : investor?.display_name}</span><strong>{event.units_delta === null ? "—" : number(event.units_delta)}</strong><span>{renderSourceAction(event)}</span></div>
                          ))}
                        </div>
                      </div>
                    )}
                  </section>
                  <aside className="share-evidence-panel">
                    {activeHolding ? (() => {
                      const currentUnits = holdingCurrentUnits(activeHolding);
                      const hasDifference = holdingHasDifference(activeHolding);
                      const snapshotIsOlder = Boolean(
                        activeHolding.position.snapshot_as_of_date &&
                        shareEventDate(activeHolding.latestEvent) &&
                        activeHolding.position.snapshot_as_of_date < shareEventDate(activeHolding.latestEvent),
                      );
                      return (
                        <div className="share-evidence-card">
                          <header><span>份额详情 · 数据依据</span><h3>{activeHolding.title}</h3><p>{activeHolding.subtitle} · 数据日 {holdingDataDate(activeHolding) || "待补充"}</p><div><span><small>当前有效份额</small><strong>{currentUnits === null ? "待建立" : number(currentUnits)}</strong></span><Status state={hasDifference ? "open" : "completed"} text={hasDifference ? "存在差异" : "来源已留痕"} /></div></header>
                          <section className="share-evidence-chain">
                            <strong>证据链</strong>
                            {activeHolding.latestEvent?.source_mail_item_id && <article><i><Mail size={12} /></i><div><strong>{activeHolding.latestEvent.source_mail_title || "投资者份额邮件"}</strong><p>原始邮件 · 接收后只读留存</p><button onClick={() => onOpenMail(activeHolding.latestEvent!.source_mail_item_id!)}>查看原始邮件 <ArrowRight size={11} /></button></div></article>}
                            {(activeHolding.latestEvent?.source_document_id || activeHolding.latestSnapshot?.source_document_id) && <article><i><FileText size={12} /></i><div><strong>{activeHolding.latestEvent?.source_document_name || "托管份额附件"}</strong><p>邮件附件 · 已关联份额记录</p>{canDownload && <a href={`/api/documents/${activeHolding.latestEvent?.source_document_id || activeHolding.latestSnapshot?.source_document_id}/download`}>下载附件 <ArrowRight size={11} /></a>}</div></article>}
                            {activeHolding.latestEvent && <article><i><Check size={12} /></i><div><strong>{shareEventLabels[activeHolding.latestEvent.event_type]} {activeHolding.latestEvent.units_delta === null ? "" : number(activeHolding.latestEvent.units_delta)}</strong><p>{shareEventStatusLabels[activeHolding.latestEvent.status]} · 原始记录保留</p></div></article>}
                            {!activeHolding.latestEvent?.source_mail_item_id && !activeHolding.latestEvent?.source_document_id && !activeHolding.latestSnapshot?.source_document_id && <p className="material-list-empty">来源标识已保存，暂无可直接打开的邮件或附件。</p>}
                          </section>
                          <div className={hasDifference ? "share-reconcile attention" : "share-reconcile"}>
                            {activeHolding.position.latest_snapshot_units !== null
                              ? snapshotIsOlder
                                ? `托管快照 ${number(activeHolding.position.latest_snapshot_units)} 早于最新份额邮件，当前份额采用后续邮件中的确认后余额。`
                                : `托管快照 ${number(activeHolding.position.latest_snapshot_units)}，台账份额 ${activeHolding.position.confirmed_units === null ? "待建立" : number(activeHolding.position.confirmed_units)}。${hasDifference ? `相差 ${number(activeHolding.position.difference)}，请到异常中心处理。` : "两者一致，无需人工核对。"}`
                              : "尚无托管快照；当前份额来自已接收的份额业务邮件。"}
                          </div>
                        </div>
                      );
                    })() : <div className="share-evidence-empty">选择一条份额记录查看邮件与附件依据。</div>}
                  </aside>
                </div>
              )}
              {tab === "events" && <ShareEventList rows={allEvents} perspective={perspective} renderSource={renderSourceAction} />}
              {tab === "snapshots" && <ShareSnapshotList rows={allSnapshots} renderSource={renderSourceAction} />}
              {tab === "sources" && <ShareSourceList events={allEvents.map(({ event }) => event)} snapshots={allSnapshots} canDownload={canDownload} onOpenMail={onOpenMail} />}
            </>
          ) : <Empty title={perspective === "investor" ? "尚未建立投资者" : "尚未建立产品"} text="建立主体并关联邮件资料后即可查看份额。" />}
        </div>
      </div>
    </section>
  );
}

function ShareEventList({
  rows,
  perspective,
  renderSource,
}: {
  rows: { event: InvestorShareEvent; investor?: ShareInvestorSummary | Investor }[];
  perspective: "investor" | "product";
  renderSource: (event?: InvestorShareEvent) => ReactNode;
}) {
  return rows.length ? <div className="share-tab-list"><div className="share-compact-table full"><div className="share-compact-row event heading"><span>业务日期</span><span>类型</span><span>{perspective === "investor" ? "产品／份额" : "投资者／份额"}</span><span>份额变动</span><span>状态</span><span>来源</span></div>{rows.map(({ event, investor }) => <div className="share-compact-row event" key={event.id}><span>{shareEventDate(event) || "待补充"}</span><span>{shareEventLabels[event.event_type]}</span><span><strong>{perspective === "investor" ? event.product_name : investor?.display_name}</strong><small>{event.share_name || "总份额"}</small></span><strong>{event.units_delta === null ? "—" : number(event.units_delta)}</strong><Status state={event.status === "pending" ? "open" : event.status} text={shareEventStatusLabels[event.status]} /><span>{renderSource(event)}</span></div>)}</div></div> : <Empty title="暂无份额变动" text="申购、赎回、分红和调整记录会按业务日期展示。" />;
}

function ShareSnapshotList({ rows, renderSource }: { rows: InvestorShareLedger["snapshots"]; renderSource: (event?: InvestorShareEvent, snapshot?: InvestorShareLedger["snapshots"][number]) => ReactNode }) {
  return rows.length ? <div className="share-tab-list"><div className="share-compact-table full"><div className="share-compact-row snapshot heading"><span>快照日期</span><span>产品</span><span>份额类别</span><span>托管份额</span><span>来源</span></div>{rows.map((snapshot) => <div className="share-compact-row snapshot" key={snapshot.id}><span>{snapshot.as_of_date}</span><span>{snapshot.product_name}</span><span>{snapshot.share_name || "总份额"}</span><strong>{number(snapshot.units)}</strong><span>{renderSource(undefined, snapshot)}</span></div>)}</div></div> : <Empty title="暂无托管快照" text="托管发送的持仓份额表会作为余额依据，不重复计算为份额变动。" />;
}

function ShareSourceList({ events, snapshots, canDownload, onOpenMail }: { events: InvestorShareEvent[]; snapshots: InvestorShareLedger["snapshots"]; canDownload: boolean; onOpenMail: (id: string) => void }) {
  const sources = [...events.map((event) => ({ key: `event:${event.id}`, date: shareEventDate(event), title: event.source_mail_title || event.source_document_name || `${event.product_name}份额业务材料`, mailId: event.source_mail_item_id, documentId: event.source_document_id, kind: "份额变动依据" })), ...snapshots.map((snapshot) => ({ key: `snapshot:${snapshot.id}`, date: snapshot.as_of_date, title: `${snapshot.product_name}托管份额快照`, mailId: snapshot.source_mail_item_id, documentId: snapshot.source_document_id, kind: "托管快照" }))].filter((source, index, rows) => rows.findIndex((candidate) => candidate.mailId && candidate.mailId === source.mailId || !candidate.mailId && candidate.documentId && candidate.documentId === source.documentId || candidate.key === source.key) === index);
  return sources.length ? <div className="share-source-grid">{sources.map((source) => <article key={source.key}><i>{source.mailId ? <Mail size={15} /> : <FileText size={15} />}</i><div><span>{source.kind}</span><strong>{source.title}</strong><small>{source.date || "日期待补充"} · 原件留存</small></div><div>{source.mailId ? <Button variant="outline" onClick={() => onOpenMail(source.mailId!)}>原始邮件</Button> : source.documentId && canDownload ? <a className="icon-link" href={`/api/documents/${source.documentId}/download`}><Download size={15} /></a> : null}</div></article>)}</div> : <Empty title="暂无来源材料" text="份额邮件和托管附件完成关联后会集中显示在这里。" />;
}

function Status({ state, text }: { state?: string; text?: string }) {
  return (
    <span
      className={
        "status " +
        (state === "review" || state === "open" || state === "liquidating"
          ? "amber"
          : state === "reversal" || state === "liquidated" || state === "archived"
            ? "clay"
            : "")
      }
    >
      <i />
      {text || stageLabel(state || "")}
    </span>
  );
}
function Empty({ title, text, children }: { title: string; text: string; children?: ReactNode }) {
  return (
    <div className="live-empty">
      <Layers3 size={30} />
      <h2>{title}</h2>
      <p>{text}</p>
      {children}
    </div>
  );
}
function PageTitle({
  eyebrow,
  title,
  text,
  children,
}: {
  eyebrow: string;
  title: string;
  text: string;
  children?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{text}</p>
      </div>
      <div className="heading-buttons">{children}</div>
    </div>
  );
}
function ErrorNote({ error }: { error?: string }) {
  return error ? (
    <p role="alert" className="form-error">
      {error}
    </p>
  ) : null;
}

function scrollableMailHtml(source: string) {
  if (source.includes('id="xuchuan-mail-scroll"')) return source;
  const viewerStyle =
    "<style>html,body{width:100%!important;height:100%!important;overflow:hidden!important}" +
    "#xuchuan-mail-scroll{box-sizing:border-box;width:100%;height:100vh;max-width:none!important;" +
    "margin:0!important;padding:24px;overflow:auto!important;scrollbar-gutter:stable}" +
    "#xuchuan-mail-scroll::-webkit-scrollbar{width:12px;height:12px}" +
    "#xuchuan-mail-scroll::-webkit-scrollbar-thumb{background:#a8aa9f;border-radius:8px}</style>";
  const withStyle = source.replace(/<\/head>/i, `${viewerStyle}</head>`);
  return withStyle
    .replace(/<body([^>]*)>/i, '<body$1><div id="xuchuan-mail-scroll">')
    .replace(/<\/body>/i, "</div></body>");
}

function MailDetailView({ item, canDownload }: { item: MailItem; canDownload: boolean }) {
  const state = useResource<MailDetail>(`/mail-items/${item.id}`, item.revision);
  const [bodyMode, setBodyMode] = useState<"html" | "text">("html");
  const bodyFrame = useRef<HTMLIFrameElement>(null);
  function scrollHtmlBody(distance: number) {
    const frame = bodyFrame.current;
    const scrollArea = frame?.contentDocument?.getElementById("xuchuan-mail-scroll");
    if (scrollArea) scrollArea.scrollBy({ left: distance, behavior: "smooth" });
  }
  if (state.loading && !state.data) return <p className="loading-copy">正在读取邮件原件…</p>;
  if (state.error) return <ErrorNote error={state.error} />;
  const detail = state.data;
  if (!detail) return null;
  return (
    <div className="mail-detail">
      <header className="mail-detail-message-head">
        <span aria-hidden="true"><Mail size={18} /></span>
        <div>
          <h3>{detail.subject}</h3>
          <p>{detail.sender || "发件人未提供"}</p>
        </div>
      </header>
      <dl className="mail-detail-meta">
        <div><dt>发件人</dt><dd>{detail.sender || "未提供"}</dd></div>
        <div><dt>收件人</dt><dd>{detail.to || "未提供"}</dd></div>
        {detail.cc && <div><dt>抄送</dt><dd>{detail.cc}</dd></div>}
        <div><dt>邮件时间</dt><dd>{detail.sent_at || "未提供"}</dd></div>
        <div><dt>系统收到</dt><dd>{timestamp(detail.received_at)}</dd></div>
        <div>
          <dt>来源</dt>
          <dd>{detail.sources.map((source) => `${source.mailbox} / ${source.folder}`).join("；") || "来源待补"}</dd>
        </div>
        <div><dt>分类</dt><dd>{mailCategoryLabel(detail.category)}</dd></div>
      </dl>
      <section className="mail-detail-section">
        <div className="mail-detail-heading">
          <h3>正文</h3>
          <div className="mail-detail-tools">
            {detail.body_html && (
              <>
                {bodyMode === "html" && (
                  <div className="mail-horizontal-controls" aria-label="横向移动正文">
                    <button type="button" onClick={() => scrollHtmlBody(-360)}><ChevronLeft size={14} />左移</button>
                    <button type="button" onClick={() => scrollHtmlBody(360)}>右移<ChevronRight size={14} /></button>
                  </div>
                )}
                <div className="mail-body-switch" aria-label="正文显示方式">
                  <button type="button" aria-pressed={bodyMode === "html"} className={bodyMode === "html" ? "active" : ""} onClick={() => setBodyMode("html")}>原始排版</button>
                  <button type="button" aria-pressed={bodyMode === "text"} className={bodyMode === "text" ? "active" : ""} onClick={() => setBodyMode("text")}>纯文本</button>
                </div>
              </>
            )}
            {canDownload && <a className="text-link" href={`/api/documents/${detail.document_id}/download`}>下载邮件原件</a>}
          </div>
        </div>
        {detail.body_html && bodyMode === "html" ? (
          <iframe
            ref={bodyFrame}
            className="mail-detail-html"
            title={`邮件正文：${detail.subject}`}
            sandbox="allow-same-origin"
            scrolling="yes"
            referrerPolicy="no-referrer"
            srcDoc={scrollableMailHtml(detail.body_html)}
          />
        ) : (
          <pre className="mail-detail-body">{detail.body || "（邮件没有可显示的文本正文，请查看附件或下载原件。）"}</pre>
        )}
      </section>
      <section className="mail-detail-section">
        <div className="mail-detail-heading">
          <h3>附件</h3>
          <span>{detail.attachments.length} 个</span>
        </div>
        {detail.attachments.length ? (
          <div className="mail-attachment-list">
            {detail.attachments.map((attachment) => (
              <article key={attachment.id}>
                <FileText size={17} />
                <div>
                  <strong>{attachment.filename}</strong>
                  <small>{attachment.media_type} · {(attachment.size / 1024).toFixed(1)} KB</small>
                </div>
                {canDownload ? (
                  <a className="icon-link" aria-label={`下载 ${attachment.filename}`} href={`/api/documents/${attachment.id}/download`}>
                    <Download size={15} />
                  </a>
                ) : <small>无下载权限</small>}
              </article>
            ))}
          </div>
        ) : <p className="inline-note">这封邮件没有归档附件。</p>}
      </section>
    </div>
  );
}

export default function App() {
  const [me, setMe] = useState<Me | null>(null),
    [loading, setLoading] = useState(true),
    [error, setError] = useState("");
  async function load() {
    setLoading(true);
    try {
      setMe(await api<Me>("/auth/me"));
      setError("");
    } catch (e) {
      if ((e as { status?: number }).status !== 401) setError((e as Error).message);
      setMe(null);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void load();
    const expired = () => setMe(null);
    window.addEventListener("session-expired", expired);
    return () => window.removeEventListener("session-expired", expired);
  }, []);
  if (loading)
    return (
      <div className="login-shell">
        <div className="brand">
          <Layers3 />
          序川
        </div>
        <p className="loading-copy">正在连接工作台…</p>
      </div>
    );
  if (!me)
    return (
      <div className="login-shell">
        <section className="login-card">
          <div className="brand">
            <span className="brand-icon">
              <Layers3 size={22} />
            </span>
            <span>
              序川<small className="brand-sub">FUND OPERATIONS</small>
            </span>
          </div>
          <div className="eyebrow">YOUR WORK, IN ORDER</div>
          <h1>让每日运营，井然有序。</h1>
          <p>登录你的机构工作台，继续今天的工作。</p>
          <ErrorNote error={error} />
          <ActionForm
            label="登录工作台"
            done={() => void load()}
            submit={(f) =>
              post("/auth/login", { email: val(f, "email"), password: String(f.get("password")) })
            }
          >
            <Field label="登录邮箱">
              <Input name="email" type="email" required autoComplete="username" />
            </Field>
            <Field label="密码">
              <Input name="password" type="password" required autoComplete="current-password" />
            </Field>
          </ActionForm>
          <div className="login-note">
            <LockKeyhole size={14} />
            <span>内部业务系统，无预设账号。首次使用请由部署管理员初始化。</span>
          </div>
        </section>
        <small className="login-foot">序川 · 基金运营工作台 / 0.1</small>
      </div>
    );
  return (
    <Workspace
      me={me}
      refreshMe={load}
      logout={async () => {
        await post("/auth/logout");
        setMe(null);
      }}
    />
  );
}

function Workspace({
  me,
  refreshMe,
  logout,
}: {
  me: Me;
  refreshMe: () => Promise<void>;
  logout: () => Promise<void>;
}) {
  const [managerId, setManagerId] = useState(me.managers[0]?.id || ""),
    [view, setView] = useState("overview"),
    [revision, setRevision] = useState(0),
    [mobile, setMobile] = useState(false),
    [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
      try {
        return window.localStorage.getItem("xuchuan.sidebar.collapsed") === "true";
      } catch {
        return false;
      }
    }),
    [modal, setModal] = useState<Modal | null>(null),
    [mailTarget, setMailTarget] = useState<{ itemId: string; request: number } | null>(null),
    [feedback, setFeedback] = useState(""),
    [search, setSearch] = useState(""),
    [materialSection, setMaterialSection] = useState<"relations" | "shares" | "documents" | "pending">("relations"),
    [materialPerspective, setMaterialPerspective] = useState<"product" | "investor">("product"),
    [investorDetailTab, setInvestorDetailTab] = useState<InvestorDetailTab>("basic"),
    [materialEntitySearch, setMaterialEntitySearch] = useState(""),
    [materialOnlyAttention, setMaterialOnlyAttention] = useState(false),
    [materialFilter, setMaterialFilter] = useState("all"),
    [materialProduct, setMaterialProduct] = useState(""),
    [materialInvestor, setMaterialInvestor] = useState(""),
    [materialCategory, setMaterialCategory] = useState(""),
    [materialSource, setMaterialSource] = useState(""),
    [materialSensitivity, setMaterialSensitivity] = useState(""),
    [materialPage, setMaterialPage] = useState(0),
    [showHiddenProducts, setShowHiddenProducts] = useState(false),
    [selectedProduct, setSelectedProduct] = useState(""),
    [selectedShare, setSelectedShare] = useState(""),
    [period, setPeriod] = useState("all");
  const [checkDate, setCheckDate] = useState("");
  const manager = me.managers.find((m) => m.id === managerId),
    perm = manager?.permissions;
  const base = manager ? `/managers/${manager.id}` : null;

  useEffect(() => {
    try {
      window.localStorage.setItem("xuchuan.sidebar.collapsed", String(sidebarCollapsed));
    } catch {
      // The layout still works when browser storage is unavailable.
    }
  }, [sidebarCollapsed]);

  const materialPageSize = 50;
  const productsState = useResource<Product[]>(
    base && (perm?.read || perm?.admin)
      ? base + (perm?.read ? "/products" : "/product-settings")
      : null,
    revision,
  );
  const filingsState = useResource<ProductFiling[]>(
    base && perm?.member ? base + "/product-filings" : null,
    revision,
  );
  const allProductsState = useResource<Product[]>(
    base && perm?.read && showHiddenProducts ? base + "/products?include_hidden=true" : null,
    revision,
  );
  const docsState = useResource<Doc[]>(
    base && perm?.archive ? base + "/documents" : null,
    revision,
  );
  const tasksState = useResource<Task[]>(base && perm?.member ? base + "/tasks" : null, revision);
  const auditState = useResource<Audit[]>(
    base && (perm?.archive || perm?.admin) ? base + "/audit" : null,
    revision,
  );
  const membersState = useResource<Member[]>(
    base && perm?.admin ? base + "/members" : null,
    revision,
  );
  const boxesState = useResource<Mailbox[]>(
    base && (perm?.archive || perm?.admin) ? base + "/mailboxes" : null,
    revision,
  );
  const investorsState = useResource<Investor[]>(
    base && perm?.investor_read ? base + "/investors" : null,
    revision,
  );
  const materialProducts = productsState.data || [];
  const materialInvestors = investorsState.data || [];
  const effectiveMaterialSection = perm?.investor_read ? materialSection : materialSection === "relations" ? "documents" : materialSection;
  const primaryMaterialProduct = materialProduct || materialProducts[0]?.id || "";
  const primaryMaterialInvestor = materialInvestor || materialInvestors[0]?.id || "";
  const effectiveMaterialProduct = effectiveMaterialSection === "relations"
    ? materialPerspective === "product" ? primaryMaterialProduct : materialProduct
    : materialProduct;
  const effectiveMaterialInvestor = effectiveMaterialSection === "relations"
    ? materialPerspective === "investor" ? primaryMaterialInvestor : materialInvestor
    : materialInvestor;
  const materialParams = new URLSearchParams({
    paginated: "true",
    limit: String(materialPageSize),
    offset: String(materialPage * materialPageSize),
    status: effectiveMaterialSection === "pending" ? "pending" : materialFilter,
  });
  if (effectiveMaterialProduct) materialParams.set("product_id", effectiveMaterialProduct);
  if (effectiveMaterialInvestor) materialParams.set("investor_id", effectiveMaterialInvestor);
  if (materialCategory) materialParams.set("category", materialCategory);
  if (materialSource) materialParams.set("source", materialSource);
  if (materialSensitivity) materialParams.set("sensitivity", materialSensitivity);
  if (search.trim()) materialParams.set("q", search.trim());
  const materialPageState = useResource<DocPage>(
    base && perm?.archive && view === "upload" && effectiveMaterialSection !== "shares"
      ? `${base}/documents?${materialParams.toString()}`
      : null,
    revision,
  );
  const receiptState = useResource<ReceiptPolicy>(base && perm?.read ? base + "/receipt-policy" : null, revision);
  const suggestedDate = receiptState.data?.suggested_valuation_date || "";
  const effectiveCheckDate = checkDate || suggestedDate;
  const summaryState = useResource<{
    expected: number;
    received: number;
    confirmed: number;
    processed_today: number | null;
    archived: number | null;
  }>(base && perm?.read && effectiveCheckDate ? base + `/summary?valuation_date=${effectiveCheckDate}` : null, revision);
  const rulesState = useResource<{ max_nav_change: string | null }>(
    base ? base + "/rules" : null,
    revision,
  );
  const products = productsState.data || [],
    displayedProducts = showHiddenProducts ? allProductsState.data || products : products,
    filings = filingsState.data || [],
    docs = docsState.data || [],
    tasks = tasksState.data || [],
    members = membersState.data || [],
    boxes = boxesState.data || [];
  const investors = investorsState.data || [];
  const p = displayedProducts.find((p) => p.id === selectedProduct) || displayedProducts[0],
    share = p?.shares.find((s) => s.id === selectedShare) || p?.shares[0];
  const historyState = useResource<History>(
    perm?.read && p && share
      ? `/products/${p.id}/nav?share_id=${encodeURIComponent(share.id)}`
      : null,
    revision,
  );
  const history = historyState.data;
  const refresh = () => setRevision((v) => v + 1);
  const done = () => {
    setModal(null);
    setMailTarget(null);
    setFeedback("已保存，业务数据已更新。");
    refresh();
  };
  useEffect(() => {
    const id = setInterval(() => {
      if (!document.hidden) refresh();
    }, 15000);
    return () => clearInterval(id);
  }, []);
  useEffect(() => {
    setSelectedProduct("");
    setSelectedShare("");
    setModal(null);
    setSearch("");
    setMaterialSection("relations");
    setMaterialPerspective("product");
    setInvestorDetailTab("basic");
    setMaterialEntitySearch("");
    setMaterialOnlyAttention(false);
    setMaterialFilter("all");
    setMaterialProduct("");
    setMaterialInvestor("");
    setMaterialCategory("");
    setMaterialSource("");
    setMaterialSensitivity("");
    setMaterialPage(0);
    setShowHiddenProducts(false);
    setFeedback("");
    setView("overview");
  }, [managerId]);
  useEffect(() => {
    if (!feedback) return;
    const id = setTimeout(() => setFeedback(""), 6000);
    return () => clearTimeout(id);
  }, [feedback]);
  async function action(fn: () => Promise<unknown>) {
    try {
      await fn();
      refresh();
    } catch (e) {
      setFeedback((e as Error).message);
    }
  }
  function go(v: string) {
    setView(v);
    if (v !== "mail") setMailTarget(null);
    setMobile(false);
    setSearch("");
  }
  function openOriginalMail(itemId: string) {
    setModal(null);
    setMailTarget((current) => ({
      itemId,
      request: (current?.request || 0) + 1,
    }));
    go("mail");
  }
  const visibleNav = navigation
    .filter((n) => !["mail", "upload"].includes(n.id) || perm?.archive)
    .filter((n) => n.id !== "exceptions" || perm?.member)
    .filter((n) => n.id !== "settings" || perm?.admin)
    .filter((n) => n.id !== "audit" || perm?.archive || perm?.admin);
  const pending = tasks.filter((t) => t.status !== "resolved");
  const pendingProductGroups = new Map<
    string,
    {
      document: Doc;
      candidate: Candidate;
      documentIds: Set<string>;
      names: Set<string>;
      shares: Set<string>;
    }
  >();
  docs.forEach((document) => {
    (document.job?.result.errors || []).forEach((error) => {
      if (!error.candidate) return;
      const candidate = error.candidate;
      const code = candidate.product_code?.trim() || "";
      const name = candidate.product_name?.trim() || "";
      const key = code
        ? `code:${code}`
        : name
          ? `name:${name}`
          : `unknown:${document.id}`;
      const group = pendingProductGroups.get(key) || {
        document,
        candidate,
        documentIds: new Set<string>(),
        names: new Set<string>(),
        shares: new Set<string>(),
      };
      group.documentIds.add(document.id);
      if (name) group.names.add(name);
      (candidate.share_class || "")
        .split(/[，,、/]/)
        .map((share) => share.trim())
        .filter(Boolean)
        .forEach((share) => group.shares.add(share));
      pendingProductGroups.set(key, group);
    });
  });
  const pendingProducts = Array.from(pendingProductGroups.values()).map((group) => ({
    document: group.document,
    sourceCount: group.documentIds.size,
    nameVariants: Array.from(group.names),
    candidate: {
      ...group.candidate,
      share_class: Array.from(group.shares).join(",") || group.candidate.share_class,
    },
  }));
  const productNames = new Map(products.map((product) => [product.id, product.name]));
  const materialDocuments = docs.filter((document) => !document.filename.toLowerCase().endsWith(".eml"));
  const unorganizedMaterials = materialDocuments.filter((document) => document.material_status !== "organized");
  const linkedMaterials = materialDocuments.filter((document) =>
    materialProductIds(document).length > 0 || (document.investor_ids?.length || 0) > 0,
  );
  const attentionMaterials = materialDocuments.filter((document) =>
    ["queued", "processing", "review"].includes(document.job?.status || ""),
  );
  const materialCounts = materialPageState.data?.counts || {
    all: materialDocuments.length,
    pending: unorganizedMaterials.length,
    linked: linkedMaterials.length,
    attention: attentionMaterials.length,
  };
  const filteredMaterials = materialPageState.data?.items || [];
  const filteredMaterialTotal = materialPageState.data?.total || 0;
  const materialNeedsAttention = (document: Doc) =>
    document.material_status !== "organized" ||
    ["queued", "processing", "review"].includes(document.job?.status || "");
  const documentsFor = (productId?: string, investorId?: string) =>
    materialDocuments.filter((document) =>
      (!productId || materialProductIds(document).includes(productId)) &&
      (!investorId || (document.investor_ids || []).includes(investorId)),
    );
  const productEntities = products.map((product) => {
    const entityDocuments = documentsFor(product.id);
    const relatedInvestorIds = new Set(
      investors
        .filter((investor) => investor.product_ids.includes(product.id))
        .map((investor) => investor.id),
    );
    entityDocuments.forEach((document) =>
      (document.investor_ids || []).forEach((id) => relatedInvestorIds.add(id)),
    );
    return {
      ...product,
      relationCount: relatedInvestorIds.size,
      materialCount: entityDocuments.length,
      attentionCount: entityDocuments.filter(materialNeedsAttention).length,
    };
  });
  const investorEntities = investors.map((investor) => {
    const entityDocuments = documentsFor(undefined, investor.id);
    const relatedProductIds = new Set(investor.product_ids);
    entityDocuments.forEach((document) =>
      materialProductIds(document).forEach((id) => relatedProductIds.add(id)),
    );
    return {
      ...investor,
      relationCount: relatedProductIds.size,
      materialCount: entityDocuments.length,
      attentionCount:
        entityDocuments.filter(materialNeedsAttention).length + (investor.status === "pending" ? 1 : 0),
    };
  });
  const selectedWorkbenchProduct =
    productEntities.find((product) => product.id === primaryMaterialProduct) || productEntities[0];
  const selectedWorkbenchInvestor =
    investorEntities.find((investor) => investor.id === primaryMaterialInvestor) || investorEntities[0];
  const searchedProductEntities = productEntities.filter((product) =>
    `${product.name} ${product.code}`.toLowerCase().includes(materialEntitySearch.trim().toLowerCase()) &&
    (!materialOnlyAttention || product.attentionCount > 0),
  );
  const searchedInvestorEntities = investorEntities.filter((investor) =>
    `${investor.display_name} ${investorTypeLabels[investor.investor_type]} ${investor.products.map((product) => product.name).join(" ")}`
      .toLowerCase()
      .includes(materialEntitySearch.trim().toLowerCase()) &&
    (!materialOnlyAttention || investor.attentionCount > 0),
  );
  const relatedWorkbenchInvestors = selectedWorkbenchProduct
    ? investorEntities
        .filter((investor) =>
          investor.product_ids.includes(selectedWorkbenchProduct.id) ||
          documentsFor(selectedWorkbenchProduct.id, investor.id).length > 0,
        )
        .map((investor) => {
          const commonDocuments = documentsFor(selectedWorkbenchProduct.id, investor.id);
          return {
            ...investor,
            commonMaterialCount: commonDocuments.length,
            commonAttentionCount: commonDocuments.filter(materialNeedsAttention).length,
          };
        })
    : [];
  const relatedWorkbenchProducts = selectedWorkbenchInvestor
    ? productEntities
        .filter((product) =>
          selectedWorkbenchInvestor.product_ids.includes(product.id) ||
          documentsFor(product.id, selectedWorkbenchInvestor.id).length > 0,
        )
        .map((product) => {
          const commonDocuments = documentsFor(product.id, selectedWorkbenchInvestor.id);
          return {
            ...product,
            commonMaterialCount: commonDocuments.length,
            commonAttentionCount: commonDocuments.filter(materialNeedsAttention).length,
          };
        })
    : [];
  const selectedRelatedInvestor = relatedWorkbenchInvestors.find((investor) => investor.id === materialInvestor);
  const selectedRelatedProduct = relatedWorkbenchProducts.find((product) => product.id === materialProduct);
  const selectedInvestorDocuments = selectedWorkbenchInvestor
    ? documentsFor(undefined, selectedWorkbenchInvestor.id)
    : [];
  const selectedInvestorGeneralDocuments = selectedInvestorDocuments.filter(
    (document) =>
      materialCategoryOf(document) === "investor_qualification" ||
      materialProductIds(document).length === 0,
  );
  const selectedInvestorBusinessDocuments =
    selectedWorkbenchInvestor && selectedRelatedProduct
      ? documentsFor(selectedRelatedProduct.id, selectedWorkbenchInvestor.id).filter(
          (document) => materialCategoryOf(document) !== "investor_qualification",
        )
      : [];
  const selectedInvestorChecklist = investorMaterialChecklist
    .filter(
      (item) =>
        selectedWorkbenchInvestor &&
        (!item.investorTypes || item.investorTypes.includes(selectedWorkbenchInvestor.investor_type)) &&
        (!item.suitabilityClasses ||
          item.suitabilityClasses.includes(selectedWorkbenchInvestor.suitability_class || "unknown")),
    )
    .map((item) => ({
      ...item,
      documents: selectedInvestorDocuments.filter((document) => {
        const haystack = (document.filename + " " + (document.title || "")).toLowerCase();
        return Boolean(
          (document.material_type && item.materialTypes?.includes(document.material_type)) ||
          item.patterns.some((pattern) => haystack.includes(pattern.toLowerCase())),
        );
      }),
    }));

  function resetMaterialFilters() {
    setMaterialCategory("");
    setMaterialSource("");
    setMaterialSensitivity("");
    setSearch("");
    setMaterialPage(0);
  }

  function renderMaterialFilters(includeSubjects: boolean) {
    return (
      <div className="material-workbench-filters">
        {includeSubjects && (
          <>
            <select aria-label="按产品筛选资料" value={materialProduct} onChange={(event) => {
              setMaterialProduct(event.target.value);
              setMaterialPage(0);
            }}>
              <option value="">全部产品</option>
              {products.map((product) => <option key={product.id} value={product.id}>{product.name}</option>)}
            </select>
            {perm?.investor_read && (
              <select aria-label="按投资者筛选资料" value={materialInvestor} onChange={(event) => {
                setMaterialInvestor(event.target.value);
                setMaterialPage(0);
              }}>
                <option value="">全部投资者</option>
                {investors.map((investor) => <option key={investor.id} value={investor.id}>{investor.display_name}</option>)}
              </select>
            )}
          </>
        )}
        <select aria-label="按资料类别筛选" value={materialCategory} onChange={(event) => {
          setMaterialCategory(event.target.value);
          setMaterialPage(0);
        }}>
          <option value="">全部类别</option>
          <option value="pending">待整理</option>
          {materialCategories.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
        <select aria-label="按资料来源筛选" value={materialSource} onChange={(event) => {
          setMaterialSource(event.target.value);
          setMaterialPage(0);
        }}>
          <option value="">全部来源</option>
          <option value="email">邮件附件</option>
          <option value="upload">手动上传</option>
          <option value="directory_import">待整理目录导入</option>
          <option value="lifecycle_material">生命周期材料</option>
        </select>
        {perm?.investor_read && (
          <select aria-label="按敏感级别筛选资料" value={materialSensitivity} onChange={(event) => {
            setMaterialSensitivity(event.target.value);
            setMaterialPage(0);
          }}>
            <option value="">全部敏感级别</option>
            <option value="standard">普通业务资料</option>
            <option value="investor_sensitive">投资者敏感资料</option>
          </select>
        )}
        <div className="search-inline">
          <Search size={15} />
          <Input
            aria-label="搜索资料"
            placeholder="搜索标题或文件名"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setMaterialPage(0);
            }}
          />
        </div>
      </div>
    );
  }

  function renderMaterialTable(relationMode: boolean, documentsOverride?: Doc[]) {
    const displayedMaterials = documentsOverride ?? filteredMaterials;
    const displayedTotal = documentsOverride?.length ?? filteredMaterialTotal;
    return (
      <>
        <ErrorNote error={materialPageState.error} />
        {displayedMaterials.length ? (
          <Table>
            <TableHeader>
              <TableRow>
                {['类别', '资料', '关联', '业务日期', '来源', '状态', '操作'].map((label) => (
                  <TableHead key={label}>{label}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {displayedMaterials.map((document) => {
                const relatedNames = relationMode && materialPerspective === "product"
                  ? document.investors?.map((investor) => investor.display_name).join("、")
                  : document.products?.map((product) => product.name).join("、") ||
                    materialProductIds(document).map((id) => productNames.get(id)).filter(Boolean).join("、");
                return (
                  <TableRow key={document.id}>
                    <TableCell>
                      <span className={`material-category ${materialCategoryOf(document) === "pending" ? "pending" : ""}`}>
                        {materialCategoryLabel(materialCategoryOf(document))}
                      </span>
                      {document.sensitivity === "investor_sensitive" && <small className="sensitive-mark">敏感资料</small>}
                    </TableCell>
                    <TableCell>
                      <div className="file-identity compact-file-identity">
                        <FileText size={17} />
                        <div>
                          <strong>{document.title || document.metadata_json.subject || document.filename}</strong>
                          <small className="block-sub">{document.filename} · {(document.size / 1024).toFixed(1)} KB</small>
                        </div>
                      </div>
                      {(!document.category || document.category === "nav_valuation") && document.job?.result.errors?.slice(0, 1).map((error, index) => (
                        <small key={index} className="parse-error">{error.reason}</small>
                      ))}
                    </TableCell>
                    <TableCell>
                      {relatedNames || (relationMode && materialPerspective === "product" ? "待关联投资者" : "待关联产品")}
                      {!relationMode && document.investors?.length ? (
                        <small className="block-sub">投资者：{document.investors.map((investor) => investor.display_name).join("、")}</small>
                      ) : null}
                    </TableCell>
                    <TableCell>
                      {document.business_date || (document.period_start ? `${document.period_start} 至 ${document.period_end || "待补充"}` : "待补充")}
                    </TableCell>
                    <TableCell>
                      {sourceLabel(document.source)}
                      {document.parent_id && <small className="block-sub">邮件附件</small>}
                      {document.organization_source === "system_parse" && (
                        <small className="block-sub">解析成功后自动整理</small>
                      )}
                      <small className="block-sub">{timestamp(document.received_at)}</small>
                    </TableCell>
                    <TableCell>
                      <Status
                        state={document.material_status === "organized" ? "completed" : document.job?.status || "open"}
                        text={
                          document.material_status === "organized"
                            ? document.organization_source === "system_parse"
                              ? "系统已整理"
                              : "已整理"
                            : document.job
                              ? undefined
                              : "待整理"
                        }
                      />
                    </TableCell>
                    <TableCell>
                      <div className="row-actions material-row-actions">
                        {perm?.write && (
                          <Button variant="outline" onClick={() => setModal({ kind: "material", document })}>
                            {document.material_status === "organized" ? "调整" : "整理"}
                          </Button>
                        )}
                        {perm?.download && (
                          <a className="icon-link" aria-label={`下载 ${document.filename}`} href={`/api/documents/${document.id}/download`}>
                            <Download size={15} />
                          </a>
                        )}
                        {perm?.write && document.job && (!document.category || document.category === "nav_valuation") &&
                          !["queued", "processing"].includes(document.job.status) && (
                            <Button variant="ghost" onClick={() => void action(() => post(`/documents/${document.id}/reparse`))}>重新解析</Button>
                          )}
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        ) : (
          <Empty
            title={materialPageState.loading ? "正在读取资料…" : materialCounts.all ? "当前范围内没有资料" : "还没有归档资料"}
            text={materialCounts.all ? "调整关系或筛选条件后再查看。" : "上传业务资料，或由只读邮箱接收附件后开始整理。"}
          >
            {perm?.write && <Button variant="outline" onClick={() => setModal({ kind: "upload" })}><Upload />上传第一份材料</Button>}
          </Empty>
        )}
        <div className="table-footer material-pagination">
          <span>{documentsOverride ? `共 ${displayedTotal} 条` : filteredMaterialTotal ? `第 ${materialPage * materialPageSize + 1}–${Math.min((materialPage + 1) * materialPageSize, filteredMaterialTotal)} 条，共 ${filteredMaterialTotal} 条` : "当前没有符合条件的资料"}</span>
          {!documentsOverride && (
          <div className="row-actions">
            <Button variant="outline" disabled={materialPage === 0 || materialPageState.loading} onClick={() => setMaterialPage((page) => Math.max(0, page - 1))}>上一页</Button>
            <Button variant="outline" disabled={(materialPage + 1) * materialPageSize >= filteredMaterialTotal || materialPageState.loading} onClick={() => setMaterialPage((page) => page + 1)}>下一页</Button>
          </div>
          )}
        </div>
      </>
    );
  }
  const shares = products.flatMap((product) => product.shares.map((s) => ({ ...s, product })));
  const allSeries = history?.series || [];
  const cutoff =
    period === "all"
      ? ""
      : new Date(Date.now() - Number(period) * 86400000).toISOString().slice(0, 10);
  const series = allSeries
    .filter((s) => !cutoff || s.date >= cutoff)
    .map((s) => ({
      ...s,
      nav: Number(s.nav),
      nav_change: Number(s.nav_change) * 100,
      nav_drawdown: Number(s.nav_drawdown) * 100,
    }));

  return (
    <div
      className={
        "app-shell " +
        (mobile ? "menu-open " : "") +
        (sidebarCollapsed ? "sidebar-collapsed" : "")
      }
    >
      {mobile && (
        <button
          className="mobile-backdrop"
          aria-label="关闭导航"
          onClick={() => setMobile(false)}
        />
      )}
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-icon">
            <Layers3 size={23} />
          </span>
          <span>
            序川<small className="brand-sub">FUND OPERATIONS</small>
          </span>
        </div>
        <div className="workspace" title={manager?.name || "当前管理人"}>
          <span className="workspace-icon">
            <Building2 size={16} />
          </span>
          <label className="manager-select">
            <small>当前管理人</small>
            <select
              aria-label="切换管理人"
              value={managerId}
              onChange={(e) => setManagerId(e.target.value)}
            >
              {me.managers.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="nav-label">工作空间</div>
        <nav aria-label="主导航">
          {visibleNav.map((n) => (
            <button
              key={n.id}
              className={"nav-link " + (view === n.id ? "active" : "")}
              aria-label={n.label}
              title={sidebarCollapsed ? n.label : undefined}
              onClick={() => {
                if (n.id === "upload") {
                  setMaterialSection(perm?.investor_read ? "relations" : "documents");
                  setMaterialPerspective("product");
                  setMaterialEntitySearch("");
                  setMaterialOnlyAttention(false);
                  setMaterialProduct("");
                  setMaterialInvestor("");
                  setMaterialCategory("");
                  setMaterialSource("");
                  setMaterialSensitivity("");
                  setMaterialFilter("all");
                  setMaterialPage(0);
                }
                go(n.id);
              }}
              aria-current={view === n.id ? "page" : undefined}
            >
              <n.icon size={17} />
              <span className="nav-link-label">{n.label}</span>
              {n.id === "exceptions" && pending.length > 0 && (
                <span className="nav-count">{pending.length}</span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="sync-note" title="业务数据每 15 秒刷新">
            <i />
            <span className="sync-note-label">业务数据每 15 秒刷新</span>
          </div>
          <div className="user">
            <span className="avatar">{me.name.slice(0, 1)}</span>
            <div>
              <strong>{me.name}</strong>
              <small>
                {perm?.write ? "运营工作空间" : perm?.admin ? "系统管理" : "只读工作空间"}
              </small>
            </div>
            <Button
              variant="ghost"
              size="icon"
              title="修改密码"
              aria-label="修改密码"
              onClick={() => setModal({ kind: "password" })}
            >
              <LockKeyhole size={14} />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              title="退出登录"
              aria-label="退出登录"
              onClick={() => void action(logout)}
            >
              <LogOut size={14} />
            </Button>
          </div>
        </div>
      </aside>
      <button
        type="button"
        className="sidebar-toggle"
        aria-label={sidebarCollapsed ? "展开侧边栏" : "收起侧边栏"}
        aria-expanded={!sidebarCollapsed}
        title={sidebarCollapsed ? "展开侧边栏" : "收起侧边栏"}
        onClick={() => setSidebarCollapsed((collapsed) => !collapsed)}
      >
        {sidebarCollapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
      </button>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            <button className="mobile-menu" aria-label="打开导航" onClick={() => setMobile(true)}>
              <Menu size={18} />
            </button>
            <span>工作空间</span>
            <ChevronRight size={13} />
            <strong>{navigation.find((n) => n.id === view)?.label}</strong>
          </div>
          <div className="top-actions">
            {!perm?.write && (
              <span className="preview-tag">
                <LockKeyhole size={11} />
                只读业务权限
              </span>
            )}
            <span>
              {new Intl.DateTimeFormat("zh-CN", {
                timeZone: "Asia/Shanghai",
                month: "long",
                day: "numeric",
                weekday: "long",
              }).format(new Date())}
            </span>
            <Button
              variant="ghost"
              size="icon"
              aria-label="刷新数据"
              title="刷新数据"
              onClick={refresh}
            >
              <RefreshCw size={15} />
            </Button>
          </div>
        </header>
        <main className="page-content" key={managerId + "-" + view}>
          {!manager ? (
            <Empty title="暂未分配牌照权限" text="请联系管理员为此账号分配管理人及角色。" />
          ) : (
            <>
              {!perm?.write && perm?.read && (
                <div className="readonly-strip">
                  <LockKeyhole size={13} />
                  当前牌照可查看，不可操作。切换到你所属的牌照后可进行运营处理。
                </div>
              )}
              <ErrorNote error={productsState.error} />
              {view === "overview" && (
                <>
                  <PageTitle
                    eyebrow="A CLEARER DAY, AHEAD"
                    title={`${me.name}，工作从容一些。`}
                    text="每日净值，资料归档，以及需要你确认的事项。"
                  >
                    {perm?.write && (
                      <Button
                        className="primary-action"
                        onClick={() => setModal({ kind: "upload" })}
                      >
                        <Upload size={15} />
                        上传材料
                      </Button>
                    )}
                  </PageTitle>
                  <div className="metrics">
                    <div>
                      <span>在管产品</span>
                      <strong>
                        {products.length}
                        <small>只</small>
                      </strong>
                      <p>当前可查看范围</p>
                    </div>
                    <div>
                      <span>已有有效净值</span>
                      <strong>
                        {shares.filter((s) => s.latest).length}
                        <small>/ {shares.length} 类份额</small>
                      </strong>
                      <p>按各份额独立记录</p>
                    </div>
                    <div>
                      <span>等待处理</span>
                      <strong>
                        {pending.length}
                        <small>项</small>
                      </strong>
                      <p>牌照内全员共享处理</p>
                    </div>
                    <div>
                      <span>归档材料</span>
                      <strong>
                        {perm?.archive ? (summaryState.data?.archived ?? docs.length) : "—"}
                        <small>份</small>
                      </strong>
                      <p>归档总数 · 含原始邮件与附件</p>
                    </div>
                  </div>
                  <section className="receipt-progress">
                    <div>
                      <Activity size={17} />
                      <strong>今日处理进度</strong>
                      <span>今日写入 / 确认事件 {summaryState.data?.processed_today ?? 0} 次</span>
                    </div>
                    <label>
                      核对估值日{" "}
                      <input
                        type="date"
                        value={effectiveCheckDate}
                        onChange={(e) => {
                          if (e.target.value) setCheckDate(e.target.value);
                        }}
                      />
                    </label>
                    <ErrorNote error={summaryState.error || receiptState.error || receiptState.data?.calendar_error || undefined} />
                    <div className="progress-track">
                      <div
                        style={{
                          width: `${summaryState.data?.expected ? (summaryState.data.confirmed / summaryState.data.expected) * 100 : 0}%`,
                        }}
                      />
                    </div>
                    <small>
                      指定估值日：应收 {summaryState.data?.expected ?? 0} 类份额 · 已收到{" "}
                      {summaryState.data?.received ?? 0} · 已有效确认{" "}
                      {summaryState.data?.confirmed ?? 0}。按交易日历和日／周频规则统计；收到材料不代表净值已确认。
                    </small>
                  </section>
                  <div className="live-overview-grid">
                    <section className="panel">
                      <div className="panel-head">
                        <div>
                          <h2>净值，一目了然</h2>
                          <p>各产品份额的最新有效数据</p>
                        </div>
                        <Button variant="ghost" onClick={() => go("nav")}>
                          查看全部
                          <ArrowRight size={14} />
                        </Button>
                      </div>
                      {shares.length ? (
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>产品 / 份额</TableHead>
                              <TableHead>单位净值</TableHead>
                              <TableHead>估值日期</TableHead>
                              <TableHead>状态</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {shares.slice(0, 6).map((s) => (
                              <TableRow key={s.id}>
                                <TableCell>
                                  <button
                                    className="text-link"
                                    onClick={() => {
                                      setSelectedProduct(s.product.id);
                                      setSelectedShare(s.id);
                                      go("nav");
                                    }}
                                  >
                                    {s.product.name}
                                  </button>
                                  <small className="block-sub">
                                    {s.name} · {s.product.code}
                                  </small>
                                </TableCell>
                                <TableCell className="numeric">
                                  {number(s.latest?.unit_nav)}
                                </TableCell>
                                <TableCell>{s.latest?.valuation_date || "—"}</TableCell>
                                <TableCell>
                                  <Status
                                    state={
                                      s.latest?.reversal
                                        ? "reversal"
                                        : s.latest
                                          ? "completed"
                                          : "open"
                                    }
                                    text={
                                      s.latest?.reversal
                                        ? "反账后"
                                        : s.latest
                                          ? "已确认"
                                          : "等待净值"
                                    }
                                  />
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      ) : (
                        <Empty
                          title="从第一只产品开始"
                          text="新建产品台账，或上传托管附件识别产品信息。"
                        >
                          {perm?.write && (
                            <Button variant="outline" onClick={() => setModal({ kind: "product" })}>
                              <Plus size={14} />
                              创建产品
                            </Button>
                          )}
                        </Empty>
                      )}
                    </section>
                    <div className="overview-side">
                      <OperationCalendar managerId={managerId} revision={revision} />
                      <section className="panel">
                      <div className="panel-head">
                        <div>
                          <h2>需要你关注</h2>
                          <p>异常有出处，处理有留痕</p>
                        </div>
                        <CircleAlert size={18} />
                      </div>
                      {pending.length ? (
                        <div className="task-peek">
                          {pending.slice(0, 4).map((t) => (
                            <button
                              key={t.id}
                              onClick={() => {
                                go("exceptions");
                                setModal({ kind: "task", task: t });
                              }}
                            >
                              <span className="task-dot" />
                              <span>
                                <strong>{taskLabel(t.kind)}</strong>
                                <small>
                                  {t.product_name} · {t.valuation_date || "请核对材料"}
                                </small>
                              </span>
                              <ChevronRight size={14} />
                            </button>
                          ))}
                        </div>
                      ) : (
                        <Empty
                          title="暂无待处理事项"
                          text="收到材料后，异常与未确认内容会汇集在这里。"
                        />
                      )}
                      </section>
                    </div>
                  </div>
                  <div className="callout">
                    <ShieldCheck size={19} />
                    <div>
                      <strong>每一个数字，都应有来处。</strong>
                      <p>
                        此工作台使用真实持久化数据。邮件原件、上传附件、处理账号与净值历史版本均分别保留。
                      </p>
                    </div>
                  </div>
                </>
              )}
              {view === "products" && (
                <>
                  <PageTitle
                    eyebrow="YOUR FUND UNIVERSE"
                    title="产品台账"
                    text="每只产品、每类份额，都有清晰的归属。"
                  >
                    {perm?.write && (
                      <div className="row-actions">
                        <Button variant="outline" onClick={() => setModal({ kind: "filing" })}>
                          新建产品备案
                        </Button>
                        <Button onClick={() => setModal({ kind: "product" })}>
                          <Plus />
                          人工创建产品
                        </Button>
                      </div>
                    )}
                  </PageTitle>
                  {pendingProducts.length > 0 && (
                    <section className="panel">
                      <div className="panel-head">
                        <div>
                          <h2>待确认产品</h2>
                          <p>来自邮件或上传附件，尚未写入正式产品台账。</p>
                        </div>
                        <span className="muted">{pendingProducts.length} 项</span>
                      </div>
                      <Table>
                        <TableHeader>
                          <TableRow>
                            {["候选产品", "份额类别", "材料来源", "操作"].map((s) => (
                              <TableHead key={s}>{s}</TableHead>
                            ))}
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {pendingProducts.map(({ document, candidate, sourceCount, nameVariants }) => (
                            <TableRow key={`${document.id}:${candidate.product_code || candidate.product_name}`}>
                              <TableCell>
                                <strong>{candidate.product_name || "名称待核对"}</strong>
                                <small className="block-sub">{candidate.product_code || "代码待核对"}</small>
                                {nameVariants.length > 1 && (
                                  <small className="parse-error">名称存在 {nameVariants.length} 种写法，请核对</small>
                                )}
                              </TableCell>
                              <TableCell>{candidate.share_class || "待核对"}</TableCell>
                              <TableCell>
                                {sourceLabel(document.source)}
                                <small className="block-sub">{document.filename}</small>
                                {sourceCount > 1 && <small className="block-sub">共 {sourceCount} 份历史材料</small>}
                              </TableCell>
                              <TableCell>
                                {perm?.write && (
                                  <Button
                                    variant="outline"
                                    onClick={() =>
                                      setModal({
                                        kind: "product",
                                        candidate,
                                        documentId: document.id,
                                      })
                                    }
                                  >
                                    核对并加入产品
                                  </Button>
                                )}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </section>
                  )}
                  {filings.filter((f) => f.status === "in_progress").length > 0 && (
                    <section className="panel">
                      <div className="panel-head">
                        <div>
                          <h2>进行中的产品备案</h2>
                          <p>第一阶段记录拟设产品；完整备案节点后续补充。</p>
                        </div>
                        <span className="muted">
                          {filings.filter((f) => f.status === "in_progress").length} 项
                        </span>
                      </div>
                      <Table>
                        <TableHeader>
                          <TableRow>
                            {['拟设产品', '份额类别', '状态', '创建时间', '操作'].map((s) => (
                              <TableHead key={s}>{s}</TableHead>
                            ))}
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {filings
                            .filter((f) => f.status === "in_progress")
                            .map((f) => (
                              <TableRow key={f.id}>
                                <TableCell>
                                  <strong>{f.name}</strong>
                                  <small className="block-sub">{f.code}</small>
                                </TableCell>
                                <TableCell>{f.shares.join(" / ")}</TableCell>
                                <TableCell><Status state={f.status} /></TableCell>
                                <TableCell>{timestamp(f.created_at)}</TableCell>
                                <TableCell>
                                  {perm?.write && (
                                    <Button
                                      variant="outline"
                                      onClick={() =>
                                        void action(() => post(`/product-filings/${f.id}/complete`))
                                      }
                                    >
                                      备案结束，加入产品
                                    </Button>
                                  )}
                                </TableCell>
                              </TableRow>
                            ))}
                        </TableBody>
                      </Table>
                    </section>
                  )}
                  <section className="panel">
                    <div className="list-tools">
                      <div className="search-inline">
                        <Search size={16} />
                        <Input
                          aria-label="搜索产品"
                          placeholder="搜索产品名称或代码"
                          value={search}
                          onChange={(e) => setSearch(e.target.value)}
                        />
                      </div>
                      <label className="check-line compact-check">
                        <input
                          type="checkbox"
                          checked={showHiddenProducts}
                          onChange={(event) => setShowHiddenProducts(event.target.checked)}
                        />
                        显示已清算及已归档
                      </label>
                      <span className="muted">
                        {displayedProducts.length} 只产品
                        {showHiddenProducts &&
                          ` · 已清算/归档 ${displayedProducts.filter((p) => ["liquidated", "archived"].includes(p.lifecycle_status)).length}`}
                      </span>
                    </div>
                    {displayedProducts.length ? (
                      <Table>
                        <TableHeader>
                          <TableRow>
                            {[
                              "产品名称",
                              "生命周期",
                              "份额类别",
                              "发送频率",
                              "接收截止",
                              "策略 / 币种",
                              "操作",
                            ].map((s) => (
                              <TableHead key={s}>{s}</TableHead>
                            ))}
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {displayedProducts
                            .filter((p) => (p.name + p.code).includes(search))
                            .map((p) => (
                              <TableRow
                                key={p.id}
                                className={
                                  ["liquidated", "archived"].includes(p.lifecycle_status)
                                    ? "muted-row"
                                    : undefined
                                }
                              >
                                <TableCell>
                                  <strong>{p.name}</strong>
                                  <small className="block-sub">{p.code}</small>
                                </TableCell>
                                <TableCell>
                                  <Status
                                    state={p.lifecycle_status}
                                    text={lifecycleLabel(p.lifecycle_status)}
                                  />
                                  {p.lifecycle_date && (
                                    <small className="block-sub">{p.lifecycle_date}</small>
                                  )}
                                </TableCell>
                                <TableCell>{p.shares.map((s) => s.name).join(" / ")}</TableCell>
                                <TableCell>
                                  {!p.expected || p.frequency === "off"
                                    ? "不纳入应收"
                                    : p.frequency === "weekly"
                                      ? "周频"
                                      : "日频"}
                                </TableCell>
                                <TableCell>{p.frequency === "daily" ? "15:00" : p.cutoff}</TableCell>
                                <TableCell>
                                  {p.strategy || "未填写"}
                                  <small className="block-sub">{p.currency}</small>
                                </TableCell>
                                <TableCell>
                                  <div className="row-actions">
                                    <Button
                                      variant="ghost"
                                      onClick={() => {
                                        setSelectedProduct(p.id);
                                        setSelectedShare("");
                                        go("nav");
                                      }}
                                    >
                                      查看
                                    </Button>
                                    {perm?.archive && (
                                      <Button
                                        variant="ghost"
                                        onClick={() => {
                                          setMaterialProduct(p.id);
                                          setMaterialInvestor("");
                                          setMaterialPerspective("product");
                                          setMaterialSection(perm?.investor_read ? "relations" : "documents");
                                          setMaterialPage(0);
                                          go("upload");
                                        }}
                                      >
                                        资料
                                      </Button>
                                    )}
                                    {perm?.write && (
                                      <Button
                                        variant="ghost"
                                        onClick={() => setModal({ kind: "upload", productId: p.id })}
                                      >
                                        上传资料
                                      </Button>
                                    )}
                                    {perm?.write && (
                                      <Button
                                        variant="ghost"
                                        onClick={() => setModal({ kind: "share", product: p })}
                                        disabled={["liquidated", "archived"].includes(
                                          p.lifecycle_status,
                                        )}
                                      >
                                        增加份额
                                      </Button>
                                    )}
                                    {perm?.admin && (
                                      <Button
                                        variant="ghost"
                                        onClick={() => setModal({ kind: "schedule", product: p })}
                                        disabled={["liquidated", "archived"].includes(
                                          p.lifecycle_status,
                                        )}
                                      >
                                        应收设置
                                      </Button>
                                    )}
                                    {perm?.admin && (
                                      <Button
                                        variant="ghost"
                                        onClick={() => setModal({ kind: "lifecycle", product: p })}
                                      >
                                        变更状态
                                      </Button>
                                    )}
                                  </div>
                                </TableCell>
                              </TableRow>
                            ))}
                        </TableBody>
                      </Table>
                    ) : (
                      <Empty
                        title={productsState.loading ? "正在读取产品…" : "暂无产品"}
                        text="可人工创建、从邮件候选确认，或在产品备案结束后转入。"
                      />
                    )}
                    <div className="table-footer">
                      <span>产品代码在同一管理人内唯一</span>
                      <span>份额独立核对 · 管理人隔离</span>
                    </div>
                  </section>
                </>
              )}
              {view === "nav" && (
                <>
                  <PageTitle
                    eyebrow="EVERY NUMBER, TRACEABLE"
                    title="净值与估值"
                    text="以有效版本呈现历史，所有原始版本保持不变。"
                  >
                    {perm?.download && (
                      <Button
                        variant="outline"
                        onClick={() => setModal({ kind: "nav-export", productId: p?.id })}
                        disabled={!products.length}
                      >
                        <Download />
                        导出 Excel
                      </Button>
                    )}
                    {perm?.write && (
                      <Button onClick={() => setModal({ kind: "nav" })} disabled={!products.length}>
                        <Plus />
                        人工补录
                      </Button>
                    )}
                  </PageTitle>
                  {p && share ? (
                    <>
                      <div className="toolbar">
                        <div className="row-actions">
                          <select
                            aria-label="选择产品"
                            value={p.id}
                            onChange={(e) => {
                              setSelectedProduct(e.target.value);
                              setSelectedShare("");
                            }}
                          >
                            {products.map((p) => (
                              <option key={p.id} value={p.id}>
                                {p.name}
                              </option>
                            ))}
                          </select>
                          <select
                            aria-label="选择份额"
                            value={share.id}
                            onChange={(e) => setSelectedShare(e.target.value)}
                          >
                            {p.shares.map((s) => (
                              <option key={s.id} value={s.id}>
                                {s.name}
                              </option>
                            ))}
                          </select>
                        </div>
                        <span className="muted">
                          {p.code} · {p.currency}
                        </span>
                      </div>
                      <div className="detail-metrics">
                        <div>
                          <span>最新单位净值</span>
                          <strong>{number(share.latest?.unit_nav)}</strong>
                          <small>估值日 {share.latest?.valuation_date || "—"}</small>
                        </div>
                        <div>
                          <span>资产净值（元）</span>
                          <strong>{number(share.latest?.net_assets, 2)}</strong>
                          <small>
                            {sourceLabel(share.latest?.source || "尚无数据")}；未跨份额汇总
                          </small>
                        </div>
                        <div>
                          <span>仓位</span>
                          <strong>
                            {share.latest?.reported_metrics.position_ratio != null
                              ? number(
                                  Number(share.latest.reported_metrics.position_ratio) * 100,
                                  2,
                                ) + "%"
                              : "—"}
                          </strong>
                          <small>仅显示附件明确披露字段</small>
                        </div>
                        <div>
                          <span>现金（元）</span>
                          <strong>{number(share.latest?.reported_metrics.cash, 2)}</strong>
                          <small>未披露字段不推测</small>
                        </div>
                      </div>
                      <ErrorNote error={historyState.error} />
                      <section className="panel">
                        <div className="panel-head">
                          <div>
                            <h2>单位净值走势</h2>
                            <p>反账后按有效版本重新展示历史曲线</p>
                          </div>
                          <select
                            aria-label="曲线时间范围"
                            value={period}
                            onChange={(e) => setPeriod(e.target.value)}
                          >
                            <option value="all">全部时间</option>
                            <option value="90">近三个月</option>
                            <option value="30">近一个月</option>
                          </select>
                        </div>
                        {series.length ? (
                          <div className="live-chart">
                            <ResponsiveContainer width="100%" height="100%">
                              <AreaChart
                                data={series}
                                margin={{ left: 10, right: 25, top: 12, bottom: 6 }}
                              >
                                <defs>
                                  <linearGradient id="navFill" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="0%" stopColor="#a9654c" stopOpacity={0.15} />
                                    <stop offset="100%" stopColor="#a9654c" stopOpacity={0} />
                                  </linearGradient>
                                </defs>
                                <CartesianGrid
                                  strokeDasharray="3 5"
                                  vertical={false}
                                  stroke="#e6e4dc"
                                />
                                <XAxis
                                  dataKey="date"
                                  tick={{ fontSize: 11 }}
                                  axisLine={false}
                                  tickLine={false}
                                />
                                <YAxis
                                  domain={[
                                    (min: number) =>
                                      Math.max(0, min - Math.max(Math.abs(min) * 0.015, 0.001)),
                                    (max: number) => max + Math.max(Math.abs(max) * 0.015, 0.001),
                                  ]}
                                  tickFormatter={(v: number) => v.toFixed(3)}
                                  tick={{ fontSize: 11 }}
                                  axisLine={false}
                                  tickLine={false}
                                />
                                <Tooltip />
                                <Area
                                  name="单位净值"
                                  type="linear"
                                  dataKey="nav"
                                  stroke="#a9654c"
                                  fill="url(#navFill)"
                                  strokeWidth={2}
                                  dot={series.length < 3}
                                  isAnimationActive={false}
                                />
                              </AreaChart>
                            </ResponsiveContainer>
                          </div>
                        ) : (
                          <Empty
                            title={historyState.loading ? "正在读取净值…" : "还没有有效净值"}
                            text="上传附件或补录数字后，通过规则的净值将在这里展示。"
                          />
                        )}
                      </section>
                      {series.length > 0 && (
                        <section className="panel panel-spaced">
                          <div className="panel-head">
                            <div>
                              <h2>净值变化与回撤</h2>
                              <p>{history?.metric_basis}。变化基准为首条有效净值。</p>
                            </div>
                          </div>
                          <div className="live-chart small-chart">
                            <ResponsiveContainer width="100%" height="100%">
                              <AreaChart data={series} margin={{ left: 10, right: 25 }}>
                                <CartesianGrid strokeDasharray="3 5" vertical={false} />
                                <XAxis dataKey="date" tick={{ fontSize: 10 }} />
                                <YAxis unit="%" tick={{ fontSize: 10 }} />
                                <Tooltip />
                                <Area
                                  name="净值变化 (%)"
                                  dataKey="nav_change"
                                  stroke="#7b8c73"
                                  fill="#7b8c73"
                                  fillOpacity={0.05}
                                  type="linear"
                                  isAnimationActive={false}
                                />
                                <Area
                                  name="净值回撤 (%)"
                                  dataKey="nav_drawdown"
                                  stroke="#b28269"
                                  fill="#b28269"
                                  fillOpacity={0.12}
                                  type="linear"
                                  isAnimationActive={false}
                                />
                              </AreaChart>
                            </ResponsiveContainer>
                          </div>
                        </section>
                      )}
                      <section className="panel panel-spaced">
                        <div className="panel-head">
                          <div>
                            <h2>历史与版本</h2>
                            <p>估值日期与材料收到时间分别记录 · 展示最近 1,000 条版本</p>
                          </div>
                        </div>
                        <Table>
                          <TableHeader>
                            <TableRow>
                              {[
                                "估值日期",
                                "单位净值",
                                "材料收到时间",
                                "来源 / 操作人",
                                "有效状态",
                                "原件",
                              ].map((s) => (
                                <TableHead key={s}>{s}</TableHead>
                              ))}
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {history?.versions.map((r) => (
                              <TableRow key={r.id}>
                                <TableCell>{r.valuation_date}</TableCell>
                                <TableCell className="numeric">{number(r.unit_nav)}</TableCell>
                                <TableCell>{timestamp(r.received_at)}</TableCell>
                                <TableCell>
                                  {sourceLabel(r.source)}
                                  <small className="block-sub">
                                    {r.actor_name ||
                                      (r.source === "manual" ? r.actor_id : "系统解析")}
                                  </small>
                                </TableCell>
                                <TableCell>
                                  <Status
                                    state={
                                      r.reversal ? "reversal" : r.effective ? "completed" : "review"
                                    }
                                    text={
                                      r.reversal
                                        ? "反账后 · 有效"
                                        : r.effective
                                          ? "当前有效"
                                          : r.validation.length
                                            ? "校验未通过"
                                            : "保留版本"
                                    }
                                  />
                                </TableCell>
                                <TableCell>
                                  {r.document_id && perm?.download && perm.all_products ? (
                                    <a
                                      className="text-link"
                                      href={`/api/documents/${r.document_id}/download`}
                                    >
                                      下载原件
                                    </a>
                                  ) : r.document_id ? (
                                    "已归档"
                                  ) : (
                                    "人工录入"
                                  )}
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </section>
                      <div className="callout">
                        <FileText size={18} />
                        <p>
                          完整持仓明细、分红及收益口径需用真实托管估值表完成适配；当前不会将空值当作零，也不把单位净值变化冒充投资者实际收益。
                        </p>
                      </div>
                    </>
                  ) : (
                    <Empty
                      title="先建立产品与份额"
                      text="每条净值必须有明确的产品、份额与估值日期。"
                    />
                  )}
                </>
              )}
              {(view === "mail" || view === "upload") && (
                <>
                  <PageTitle
                    eyebrow={view === "mail" ? "THE ORIGINAL, ALWAYS" : "FROM MATERIAL TO DATA"}
                    title={view === "mail" ? "邮件中心" : "资料中心"}
                    text={
                      view === "mail"
                        ? "按接收邮箱查看全部已归档邮件，点击列表直接阅读正文和附件。"
                        : "从产品或投资者出发，查看双方关系及其共同资料；原件、整理结果和处理记录始终可以追溯。"
                    }
                  >
                    {view === "mail" && perm?.write && (
                      <Button onClick={() => setModal({ kind: "upload" })}>
                        <Upload />
                        上传资料
                      </Button>
                    )}
                    {view === "upload" && perm?.write && (
                      <Button onClick={() => setModal({ kind: "upload" })}>
                        <Upload />
                        上传资料
                      </Button>
                    )}
                    {view === "upload" && perm?.investor_write && (
                      <Button variant="outline" onClick={() => setModal({ kind: "investor" })}>
                        <Plus />
                        建立投资者
                      </Button>
                    )}
                  </PageTitle>
                  <ErrorNote error={docsState.error} />
                  {view === "mail" && base && (
                    <MailWorkspace key={managerId} base={base} boxes={boxes} boxesError={boxesState.error}
                      revision={revision} canWrite={Boolean(perm?.write)} canManageShares={Boolean(perm?.investor_write)}
                      target={mailTarget}
                      renderDetail={(item) => <MailDetailView key={item.id} item={item} canDownload={Boolean(perm?.download)} />}
                      onAction={(item) => setModal({ kind: "mail-action", item })}
                      onClassify={(item) => setModal({ kind: "mail-classify", item })}
                      onShareEvent={(item) => setModal({ kind: "share-event", sourceMail: item })}
                      onPositionSnapshot={(item) => setModal({ kind: "position-snapshot", sourceMail: item })} />
                  )}
                  {view === "upload" && (
                    <>
                      <div className="view-tabs material-primary-tabs" aria-label="资料中心视图">
                        {perm?.investor_read && (
                          <button
                            className={effectiveMaterialSection === "relations" ? "current" : ""}
                            onClick={() => {
                              setMaterialSection("relations");
                              setMaterialFilter("all");
                              resetMaterialFilters();
                            }}
                          >
                            关系工作台
                          </button>
                        )}
                        {perm?.investor_read && (
                          <button
                            className={effectiveMaterialSection === "shares" ? "current" : ""}
                            onClick={() => {
                              setMaterialSection("shares");
                              setMaterialFilter("all");
                              setMaterialProduct("");
                              setMaterialInvestor("");
                              resetMaterialFilters();
                            }}
                          >
                            投资者份额
                          </button>
                        )}
                        <button
                          className={effectiveMaterialSection === "documents" ? "current" : ""}
                          onClick={() => {
                            setMaterialSection("documents");
                            setMaterialFilter("all");
                            setMaterialProduct("");
                            setMaterialInvestor("");
                            resetMaterialFilters();
                          }}
                        >
                          全部资料
                        </button>
                        <button
                          className={effectiveMaterialSection === "pending" ? "current" : ""}
                          onClick={() => {
                            setMaterialSection("pending");
                            setMaterialFilter("pending");
                            setMaterialProduct("");
                            setMaterialInvestor("");
                            resetMaterialFilters();
                          }}
                        >
                          待整理 <small>{materialCounts.pending}</small>
                        </button>
                      </div>

                      {effectiveMaterialSection === "shares" && base && (
                        <InvestorShareWorkspace
                          revision={revision}
                          investors={investors}
                          products={products}
                          canDownload={Boolean(perm?.download)}
                          onOpenMail={openOriginalMail}
                        />
                      )}

                      {effectiveMaterialSection === "relations" && (
                        <section className="material-workbench panel">
                          <div className="material-workbench-toolbar">
                            <div className="material-direction" aria-label="关系查看方向">
                              <button
                                className={materialPerspective === "product" ? "current" : ""}
                                onClick={() => {
                                  setMaterialPerspective("product");
                                  setMaterialProduct(materialProduct || selectedRelatedProduct?.id || products[0]?.id || "");
                                  setMaterialInvestor("");
                                  setMaterialPage(0);
                                }}
                              >
                                按产品
                              </button>
                              <button
                                className={materialPerspective === "investor" ? "current" : ""}
                                onClick={() => {
                                  setMaterialPerspective("investor");
                                  setInvestorDetailTab("basic");
                                  setMaterialInvestor(materialInvestor || selectedRelatedInvestor?.id || investors[0]?.id || "");
                                  setMaterialProduct("");
                                  setMaterialPage(0);
                                }}
                              >
                                按投资者
                              </button>
                            </div>
                            <div className="search-inline material-entity-search">
                              <Search size={15} />
                              <Input
                                aria-label={materialPerspective === "product" ? "搜索产品" : "搜索投资者"}
                                placeholder={materialPerspective === "product" ? "搜索产品名称或代码" : "搜索投资者名称或类型"}
                                value={materialEntitySearch}
                                onChange={(event) => setMaterialEntitySearch(event.target.value)}
                              />
                            </div>
                            <Button
                              variant={materialOnlyAttention ? "outline" : "ghost"}
                              aria-pressed={materialOnlyAttention}
                              onClick={() => setMaterialOnlyAttention((value) => !value)}
                            >
                              {materialOnlyAttention ? "已筛选有待办" : "仅看有待办"}
                            </Button>
                          </div>

                          <div className="material-workbench-grid">
                            <aside className="material-entity-panel">
                              <div className="material-entity-heading">
                                <strong>{materialPerspective === "product" ? "产品" : "投资者"}</strong>
                                <span>{materialPerspective === "product" ? searchedProductEntities.length : searchedInvestorEntities.length} 个主体</span>
                              </div>
                              <div className="material-entity-list">
                                {materialPerspective === "product" ? searchedProductEntities.map((product) => (
                                  <button
                                    key={product.id}
                                    className={selectedWorkbenchProduct?.id === product.id ? "current" : ""}
                                    onClick={() => {
                                      setMaterialProduct(product.id);
                                      setMaterialInvestor("");
                                      setMaterialPage(0);
                                    }}
                                  >
                                    <span className="material-entity-name"><i />{product.name}</span>
                                    <small>{product.code}</small>
                                    <span className="material-entity-counts">
                                      <small>{product.relationCount} 个关联</small>
                                      <small>{product.materialCount} 份资料</small>
                                      <small className={product.attentionCount ? "attention" : ""}>{product.attentionCount} 待核对</small>
                                    </span>
                                  </button>
                                )) : searchedInvestorEntities.map((investor) => (
                                  <button
                                    key={investor.id}
                                    className={selectedWorkbenchInvestor?.id === investor.id ? "current" : ""}
                                    onClick={() => {
                                      setMaterialInvestor(investor.id);
                                      setInvestorDetailTab("basic");
                                      setMaterialProduct("");
                                      setMaterialPage(0);
                                    }}
                                  >
                                    <span className="material-entity-name"><i />{investor.display_name}</span>
                                    <small>{investorTypeLabels[investor.investor_type]} · {investorStatusLabels[investor.status]}</small>
                                    <span className="material-entity-counts">
                                      <small>{investor.relationCount} 个关联</small>
                                      <small>{investor.materialCount} 份资料</small>
                                      <small className={investor.attentionCount ? "attention" : ""}>{investor.attentionCount} 待核对</small>
                                    </span>
                                  </button>
                                ))}
                                {!searchedProductEntities.length && materialPerspective === "product" && (
                                  <p className="material-list-empty">没有符合条件的产品。</p>
                                )}
                                {!searchedInvestorEntities.length && materialPerspective === "investor" && (
                                  <p className="material-list-empty">没有符合条件的投资者。</p>
                                )}
                              </div>
                            </aside>

                            <div className="material-relation-content">
                              {(materialPerspective === "product" ? selectedWorkbenchProduct : selectedWorkbenchInvestor) ? (
                                <>
                                  <header className="material-subject">
                                    <div>
                                      <span>当前{materialPerspective === "product" ? "产品" : "投资者"}</span>
                                      <h2>{materialPerspective === "product" ? selectedWorkbenchProduct?.name : selectedWorkbenchInvestor?.display_name}</h2>
                                      <p>
                                        {materialPerspective === "product"
                                          ? `${selectedWorkbenchProduct?.code || "产品代码待补"} · 关系与资料仅作运营归档和核对`
                                          : `${investorTypeLabels[selectedWorkbenchInvestor?.investor_type || "other"]} · ${investorStatusLabels[selectedWorkbenchInvestor?.status || "pending"]} · ${investorSourceLabels[selectedWorkbenchInvestor?.source || "manual"]}`}
                                      </p>
                                    </div>
                                    <div className="material-subject-side">
                                      {perm?.write && materialPerspective === "product" && selectedWorkbenchProduct && (
                                        <Button onClick={() => setModal({ kind: "upload", productId: selectedWorkbenchProduct.id })}>
                                          <Upload size={14} />
                                          上传到该产品
                                        </Button>
                                      )}
                                      {perm?.write && materialPerspective === "investor" && selectedWorkbenchInvestor && (
                                        <Button onClick={() => setModal({ kind: "upload", investorId: selectedWorkbenchInvestor.id })}>
                                          <Upload size={14} />
                                          上传到该投资者
                                        </Button>
                                      )}
                                      {materialPerspective === "investor" && selectedWorkbenchInvestor && perm?.investor_write && (
                                        <Button variant="outline" onClick={() => setModal({ kind: "investor", investor: selectedWorkbenchInvestor })}>编辑投资者</Button>
                                      )}
                                      <div className="material-subject-stats">
                                        <div><span>关联{materialPerspective === "product" ? "投资者" : "产品"}</span><strong>{materialPerspective === "product" ? selectedWorkbenchProduct?.relationCount : selectedWorkbenchInvestor?.relationCount}</strong></div>
                                        <div><span>资料</span><strong>{materialPerspective === "product" ? selectedWorkbenchProduct?.materialCount : selectedWorkbenchInvestor?.materialCount}</strong></div>
                                        <div className="attention"><span>待核对</span><strong>{materialPerspective === "product" ? selectedWorkbenchProduct?.attentionCount : selectedWorkbenchInvestor?.attentionCount}</strong></div>
                                      </div>
                                    </div>
                                  </header>

                                  {materialPerspective === "investor" && (
                                    <nav className="investor-detail-tabs" aria-label="投资者资料分区">
                                      {([
                                        ["basic", "基本信息"],
                                        ["suitability", "适当性"],
                                        ["accounts", "银行账户"],
                                        ["general", "通用资料"],
                                        ["business", "产品业务资料"],
                                      ] as [InvestorDetailTab, string][]).map(([tab, label]) => (
                                        <button
                                          key={tab}
                                          className={investorDetailTab === tab ? "current" : ""}
                                          onClick={() => {
                                            setInvestorDetailTab(tab);
                                            if (tab !== "business") setMaterialProduct("");
                                            setMaterialPage(0);
                                          }}
                                        >
                                          {label}
                                        </button>
                                      ))}
                                    </nav>
                                  )}

                                  {(materialPerspective === "product" || investorDetailTab === "business") && (
                                  <section className="material-relations">
                                    <div className="material-section-heading">
                                      <strong>关联{materialPerspective === "product" ? "投资者" : "产品"}</strong>
                                      <span>选择后只看双方共同资料</span>
                                    </div>
                                    <div className="material-relation-list">
                                      {materialPerspective === "product" ? relatedWorkbenchInvestors.map((investor) => (
                                        <button
                                          key={investor.id}
                                          className={materialInvestor === investor.id ? "current" : ""}
                                          onClick={() => {
                                            setMaterialInvestor(materialInvestor === investor.id ? "" : investor.id);
                                            setMaterialPage(0);
                                          }}
                                        >
                                          <strong>{investor.display_name}</strong>
                                          <small>{investorTypeLabels[investor.investor_type]} · {investorStatusLabels[investor.status]}</small>
                                          <span><small>{investor.commonMaterialCount} 份资料</small><small className={investor.commonAttentionCount ? "attention" : ""}>{investor.commonAttentionCount ? `待核对 ${investor.commonAttentionCount}` : "已核对"}</small></span>
                                        </button>
                                      )) : relatedWorkbenchProducts.map((product) => (
                                        <button
                                          key={product.id}
                                          className={materialProduct === product.id ? "current" : ""}
                                          onClick={() => {
                                            setMaterialProduct(materialProduct === product.id ? "" : product.id);
                                            setMaterialPage(0);
                                          }}
                                        >
                                          <strong>{product.name}</strong>
                                          <small>{product.code}</small>
                                          <span><small>{product.commonMaterialCount} 份资料</small><small className={product.commonAttentionCount ? "attention" : ""}>{product.commonAttentionCount ? `待核对 ${product.commonAttentionCount}` : "已核对"}</small></span>
                                        </button>
                                      ))}
                                      {materialPerspective === "product" && !relatedWorkbenchInvestors.length && <p className="material-list-empty">该产品尚未关联投资者。</p>}
                                      {materialPerspective === "investor" && !relatedWorkbenchProducts.length && <p className="material-list-empty">该投资者尚未关联产品。</p>}
                                    </div>
                                  </section>
                                  )}

                                  {materialPerspective === "investor" && investorDetailTab === "basic" && selectedWorkbenchInvestor && (
                                    <section className="investor-profile-section">
                                      <div className="investor-profile-heading">
                                        <div>
                                          <strong>投资者基础信息</strong>
                                          <span>主体身份与适当性分类分别记录</span>
                                        </div>
                                        <Status state={selectedWorkbenchInvestor.status} text={investorStatusLabels[selectedWorkbenchInvestor.status]} />
                                      </div>
                                      <dl className="investor-field-grid">
                                        <div><dt>主体类型</dt><dd>{investorTypeLabels[selectedWorkbenchInvestor.investor_type]}</dd></div>
                                        <div><dt>适当性类型</dt><dd>{suitabilityClassLabels[selectedWorkbenchInvestor.suitability_class || "unknown"]}</dd></div>
                                        <div><dt>证件类型</dt><dd>{selectedWorkbenchInvestor.certificate_type || "待补充"}</dd></div>
                                        <div><dt>证件号码</dt><dd>{selectedWorkbenchInvestor.certificate_number_masked || "待补充"}</dd></div>
                                        <div><dt>证件有效期</dt><dd>{selectedWorkbenchInvestor.certificate_valid_until || "待补充"}</dd></div>
                                        <div><dt>国籍／注册地</dt><dd>{selectedWorkbenchInvestor.nationality_or_region || "待补充"}</dd></div>
                                        <div><dt>联系邮箱</dt><dd>{selectedWorkbenchInvestor.contact_email || "待补充"}</dd></div>
                                        <div><dt>联系电话</dt><dd>{selectedWorkbenchInvestor.contact_phone || "待补充"}</dd></div>
                                      </dl>
                                      {selectedWorkbenchInvestor.notes && (
                                        <div className="investor-profile-note">
                                          <span>档案备注</span>
                                          <p>{selectedWorkbenchInvestor.notes}</p>
                                        </div>
                                      )}
                                      <div className="investor-related-products">
                                        <div className="material-section-heading">
                                          <strong>关联产品</strong>
                                          <span>{relatedWorkbenchProducts.length} 只</span>
                                        </div>
                                        <div className="investor-product-chips">
                                          {relatedWorkbenchProducts.map((product) => (
                                            <button
                                              key={product.id}
                                              onClick={() => {
                                                setInvestorDetailTab("business");
                                                setMaterialProduct(product.id);
                                                setMaterialPage(0);
                                              }}
                                            >
                                              <strong>{product.name}</strong>
                                              <small>{product.code}</small>
                                            </button>
                                          ))}
                                          {!relatedWorkbenchProducts.length && <span className="material-list-empty">尚未关联产品</span>}
                                        </div>
                                      </div>
                                    </section>
                                  )}

                                  {materialPerspective === "investor" && investorDetailTab === "suitability" && selectedWorkbenchInvestor && (
                                    <section className="investor-profile-section">
                                      <div className="investor-profile-heading">
                                        <div>
                                          <strong>适当性信息</strong>
                                          <span>当前字段与归档原件分开呈现</span>
                                        </div>
                                      </div>
                                      <dl className="investor-field-grid compact">
                                        <div><dt>投资者分类</dt><dd>{suitabilityClassLabels[selectedWorkbenchInvestor.suitability_class || "unknown"]}</dd></div>
                                        <div><dt>专业投资者类型</dt><dd>{selectedWorkbenchInvestor.professional_investor_type || "不适用／待补充"}</dd></div>
                                        <div><dt>风险等级</dt><dd>{selectedWorkbenchInvestor.risk_level || "待补充"}</dd></div>
                                        <div><dt>测评日期</dt><dd>{selectedWorkbenchInvestor.risk_assessed_at || "待补充"}</dd></div>
                                        <div><dt>测评到期日</dt><dd>{selectedWorkbenchInvestor.risk_expires_at || "待补充"}</dd></div>
                                        <div><dt>特定对象确认</dt><dd>{specificObjectStatusLabels[selectedWorkbenchInvestor.specific_object_status || "unknown"]}</dd></div>
                                        <div><dt>合格材料状态</dt><dd>{qualifiedMaterialStatusLabels[selectedWorkbenchInvestor.qualified_material_status || "unknown"]}</dd></div>
                                        <div><dt>材料有效期间</dt><dd>{selectedWorkbenchInvestor.qualified_material_from || "待补充"} 至 {selectedWorkbenchInvestor.qualified_material_until || "待补充"}</dd></div>
                                      </dl>
                                      <div className="investor-checklist">
                                        <div className="material-section-heading">
                                          <strong>适当性资料</strong>
                                          <span>清单随主体类型和普通／专业分类变化；优先使用资料细类，旧资料兼容文件名归纳</span>
                                        </div>
                                        <div className="investor-checklist-grid">
                                          {selectedInvestorChecklist.map((item) => (
                                            <div key={item.key} className={item.documents.length ? "present" : ""}>
                                              <i>{item.documents.length ? "✓" : "—"}</i>
                                              <span><strong>{item.label}</strong><small>{item.documents.length ? "已归档 " + item.documents.length + " 份" : "待补充"}</small></span>
                                            </div>
                                          ))}
                                        </div>
                                      </div>
                                    </section>
                                  )}

                                  {materialPerspective === "investor" && investorDetailTab === "accounts" && selectedWorkbenchInvestor && (
                                    <section className="investor-profile-section">
                                      <div className="investor-profile-heading">
                                        <div>
                                          <strong>银行账户</strong>
                                          <span>一个投资者可以登记多个账户，并可指定关联产品</span>
                                        </div>
                                        {perm?.investor_write && (
                                          <Button variant="outline" onClick={() => setModal({ kind: "bank-account", investor: selectedWorkbenchInvestor })}>
                                            <Plus size={14} />新增账户
                                          </Button>
                                        )}
                                      </div>
                                      {selectedWorkbenchInvestor.bank_accounts?.length ? (
                                        <div className="investor-account-list">
                                          {selectedWorkbenchInvestor.bank_accounts.map((account) => (
                                            <div key={account.id}>
                                              <span><strong>{account.account_name}</strong><small>{account.status === "active" ? "有效" : "已停用"}</small></span>
                                              <p>{account.account_number_masked}</p>
                                              <small>{account.bank_name} · {account.branch_name || "开户行待补充"} · {account.currency}</small>
                                              {perm?.investor_write && <Button variant="ghost" onClick={() => setModal({ kind: "bank-account", investor: selectedWorkbenchInvestor, account })}>编辑账户</Button>}
                                            </div>
                                          ))}
                                        </div>
                                      ) : (
                                        <Empty title="暂无银行账户信息" text="账户字段将在录入后脱敏显示；账户证明原件继续归档在投资者资料中。">
                                          {perm?.investor_write && <Button variant="outline" onClick={() => setModal({ kind: "bank-account", investor: selectedWorkbenchInvestor })}><Plus size={14} />新增账户</Button>}
                                        </Empty>
                                      )}
                                    </section>
                                  )}

                                  {(materialPerspective === "product" || investorDetailTab === "general" || (investorDetailTab === "business" && selectedRelatedProduct)) && (
                                  <>
                                  <div className="material-scope">
                                    <span>当前范围</span>
                                    <strong>{materialPerspective === "product" ? selectedWorkbenchProduct?.name : selectedWorkbenchInvestor?.display_name}</strong>
                                    {(selectedRelatedInvestor || selectedRelatedProduct) && <ArrowRight size={13} />}
                                    {(selectedRelatedInvestor || selectedRelatedProduct) && <strong>{selectedRelatedInvestor?.display_name || selectedRelatedProduct?.name}</strong>}
                                    <b>
                                      {materialPerspective === "investor"
                                        ? investorDetailTab === "general"
                                          ? "通用资料 " + selectedInvestorGeneralDocuments.length
                                          : "产品业务资料 " + selectedInvestorBusinessDocuments.length
                                        : selectedRelatedInvestor
                                          ? "共同资料 " + filteredMaterialTotal
                                          : "全部资料 " + filteredMaterialTotal}
                                    </b>
                                    {(selectedRelatedInvestor || selectedRelatedProduct) && (
                                      <button onClick={() => {
                                        if (materialPerspective === "product") setMaterialInvestor("");
                                        else setMaterialProduct("");
                                        setMaterialPage(0);
                                      }}>清除关联 <X size={12} /></button>
                                    )}
                                  </div>
                                  {materialPerspective === "product" && renderMaterialFilters(false)}
                                  <div className="material-table-wrap">
                                    {renderMaterialTable(
                                      true,
                                      materialPerspective === "investor"
                                        ? investorDetailTab === "general"
                                          ? selectedInvestorGeneralDocuments
                                          : selectedInvestorBusinessDocuments
                                        : undefined,
                                    )}
                                  </div>
                                  </>
                                  )}
                                  {materialPerspective === "investor" && investorDetailTab === "business" && !selectedRelatedProduct && (
                                    <Empty title="请选择关联产品" text="选择上方产品后查看该投资者与产品之间的合同、认申购、赎回和其他共同资料。" />
                                  )}
                                </>
                              ) : (
                                <Empty
                                  title={materialPerspective === "product" ? "尚未建立产品" : "尚未建立投资者"}
                                  text={materialPerspective === "product" ? "先在产品台账建立产品后再关联资料。" : "建立投资者后即可查看其产品和共同资料。"}
                                >
                                  {materialPerspective === "investor" && perm?.investor_write && <Button variant="outline" onClick={() => setModal({ kind: "investor" })}><Plus />建立投资者</Button>}
                                </Empty>
                              )}
                            </div>
                          </div>
                        </section>
                      )}

                      {(effectiveMaterialSection === "documents" || effectiveMaterialSection === "pending") && (
                        <section className="panel material-center-panel material-flat-panel">
                          <div className="list-tools material-list-heading">
                            <div>
                              <h2>{effectiveMaterialSection === "pending" ? "待整理资料" : "全部资料"}</h2>
                              <p>{effectiveMaterialSection === "pending" ? "补充类别、主体和业务日期后形成可查询的资料关系。" : "按主体、类别、来源和敏感级别查询归档资料。"}</p>
                            </div>
                            {renderMaterialFilters(true)}
                          </div>
                          {renderMaterialTable(false)}
                        </section>
                      )}

                      {effectiveMaterialSection === "relations" && (
                        <div className="callout material-permission-note">
                          <ShieldCheck size={18} />
                          <p>投资者及其关联资料只向本牌照有权限的运营、管理员及合规角色开放；关系工作台不计算持有份额，也不代替托管平台执行申购或赎回。</p>
                        </div>
                      )}
                    </>
                  )}
                </>
              )}
              {view === "exceptions" && (
                <>
                  <PageTitle
                    eyebrow="A LITTLE ATTENTION, A LOT OF CLARITY"
                    title="异常中心"
                    text="当前牌照全员共享处理，无需领取；每个结论都有账号、有依据。"
                  >
                    {perm?.write && (
                      <Button variant="outline" onClick={() => setModal({ kind: "check" })}>
                        检查应收材料
                      </Button>
                    )}
                  </PageTitle>
                  <ErrorNote error={tasksState.error} />
                  <ErrorNote error={receiptState.error || receiptState.data?.error || receiptState.data?.calendar_error || undefined} />
                  <p className="inline-note">自动应收：{receiptState.data?.enabled ? "已启用" : "未启用，请在组织与权限配置"}。15:00 截止；下一交易日 {receiptState.data?.followup_time || "09:00"} 仍缺件时提示核查。最近检查：{receiptState.data?.last_checked_at ? timestamp(receiptState.data.last_checked_at) : "尚未执行"}。</p>
                  <div className="toolbar">
                    <div className="view-tabs">
                      <button
                        className={search !== "resolved" ? "current" : ""}
                        onClick={() => setSearch("")}
                      >
                        待处理 {pending.length}
                      </button>
                      <button
                        className={search === "resolved" ? "current" : ""}
                        onClick={() => setSearch("resolved")}
                      >
                        已解决 {tasks.filter((t) => t.status === "resolved").length}
                      </button>
                    </div>
                    <span className="muted">{manager.name} · 共享队列</span>
                  </div>
                  <section className="panel">
                    {tasks.filter((t) =>
                      search === "resolved" ? t.status === "resolved" : t.status !== "resolved",
                    ).length ? (
                      <Table>
                        <TableHeader>
                          <TableRow>
                            {["事项", "产品 / 估值日", "状态", "创建时间", "操作"].map(
                              (s) => (
                                <TableHead key={s}>{s}</TableHead>
                              ),
                            )}
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {tasks
                            .filter((t) =>
                              search === "resolved"
                                ? t.status === "resolved"
                                : t.status !== "resolved",
                            )
                            .map((t) => (
                              <TableRow key={t.id}>
                                <TableCell>
                                  <strong>{t.kind === "missing" ? (t.payload.stage === "followup" ? "持续缺件 · 请核查托管补发" : "净值材料迟到") : taskLabel(t.kind)}</strong>
                                  <small className="block-sub">
                                    {t.payload.errors?.[0]?.reason ||
                                      t.payload.errors?.[0]?.message ||
                                      t.payload.error ||
                                      "查看依据后处理"}
                                  </small>
                                </TableCell>
                                <TableCell>
                                  {t.product_name}
                                  <small className="block-sub">
                                    {t.valuation_date || "待识别"}
                                  </small>
                                </TableCell>
                                <TableCell>
                                  <Status state={t.status} />
                                </TableCell>
                                <TableCell>{timestamp(t.created_at)}</TableCell>
                                <TableCell>
                                  <div className="row-actions">
                                    {t.mail_item_id && perm?.archive &&
                                      (t.mail_item_category !== "investor_redemption" || perm.investor_read) && (
                                        <Button variant="ghost" onClick={() => openOriginalMail(t.mail_item_id!)}>
                                          <Mail size={13} />
                                          原始邮件
                                        </Button>
                                      )}
                                    <Button
                                      variant="ghost"
                                      onClick={() => setModal({ kind: "task", task: t })}
                                    >
                                      查看与处理
                                      <ChevronRight size={13} />
                                    </Button>
                                  </div>
                                </TableCell>
                              </TableRow>
                            ))}
                        </TableBody>
                      </Table>
                    ) : (
                      <Empty
                        title="这里暂时没有待办"
                        text="缺失、冲突和解析异常会自动汇集，已解决事项仍可追溯。"
                      />
                    )}
                  </section>
                </>
              )}
              {view === "audit" && (
                <>
                  <PageTitle
                    eyebrow="A RECORD OF EVERY STEP"
                    title="业务留痕"
                    text="产品建档、数据确认、权限调整与材料下载，按发生顺序记录。"
                  />
                  <ErrorNote error={auditState.error} />
                  <section className="panel">
                    <div className="panel-head">
                      <h2>最近 500 条操作记录</h2>
                      <ShieldCheck size={18} />
                    </div>
                    {auditState.data?.length ? (
                      <div className="audit-feed">
                        {auditState.data.map((a) => (
                          <article key={a.id}>
                            <span className="audit-icon">
                              <Check size={14} />
                            </span>
                            <div>
                              <strong>{a.actor_name}</strong>
                              <span className="audit-action">{a.action}</span>
                              <small>{timestamp(a.created_at)}</small>
                              <details>
                                <summary>查看依据与对象标识</summary>
                                <p>{a.object_id}</p>
                                <pre>{JSON.stringify(a.details, null, 2)}</pre>
                              </details>
                            </div>
                          </article>
                        ))}
                      </div>
                    ) : (
                      <Empty title="暂无操作记录" text="发生业务操作后，记录会出现在这里。" />
                    )}
                  </section>
                </>
              )}
              {view === "settings" && (
                <>
                  <PageTitle
                    eyebrow="THE RIGHT ACCESS, IN THE RIGHT PLACE"
                    title="组织与权限"
                    text="按牌照授权；一个账号可以属于多个牌照。"
                  >
                    {perm?.admin && (
                      <Button onClick={() => setModal({ kind: "member" })}>
                        <Plus />
                        创建成员
                      </Button>
                    )}
                  </PageTitle>
                  <ErrorNote error={membersState.error} />
                  <ErrorNote error={receiptState.error} />
                  {perm?.admin && receiptState.data && <ReceiptSettings key={managerId + String(receiptState.data.enabled) + receiptState.data.followup_time} managerId={managerId} policy={receiptState.data} done={done} />}
                  <section className="panel">
                    <div className="panel-head">
                      <h2>成员与角色</h2>
                      <span className="muted">{manager.name}</span>
                    </div>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          {["成员", "角色", "下载权限", "操作"].map((s) => (
                            <TableHead key={s}>{s}</TableHead>
                          ))}
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {members.map((m) => (
                          <TableRow key={m.user_id}>
                            <TableCell>
                              <strong>{m.name}</strong>
                              <small className="block-sub">{m.email}</small>
                            </TableCell>
                            <TableCell>
                              {m.roles.map((r) => roles[r] || r).join("、") || "已移除本牌照授权"}
                            </TableCell>
                            <TableCell>{m.can_download ? "已授权" : "未授权"}</TableCell>
                            <TableCell>
                              <Button
                                variant="ghost"
                                onClick={() => setModal({ kind: "member", member: m })}
                              >
                                调整授权
                              </Button>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </section>
                  <section className="panel panel-spaced">
                    <div className="panel-head">
                      <div>
                        <h2>净值校验规则</h2>
                        <p>单位净值为正、日期及币种等硬性规则始终启用。</p>
                        <p>
                          相邻有效估值日变化阈值：
                          {rulesState.data?.max_nav_change
                            ? number(Number(rulesState.data.max_nav_change) * 100, 2) + "%"
                            : "未启用，等待管理员配置"}
                        </p>
                      </div>
                      <Button variant="outline" onClick={() => setModal({ kind: "rules" })}>
                        配置异常阈值
                      </Button>
                    </div>
                  </section>
                  <section className="panel panel-spaced">
                    <div className="panel-head">
                      <div>
                        <h2>邮箱接入</h2>
                        <p>管理员可管理多个邮箱；授权码加密保存且永不回显。</p>
                      </div>
                      <Button variant="outline" onClick={() => setModal({ kind: "mailbox" })}>
                        <Plus />
                        登记邮箱
                      </Button>
                    </div>
                    {boxes.length ? (
                      <Table>
                        <TableHeader>
                          <TableRow>
                            {["邮箱", "同步范围", "最近同步", "状态", "操作"].map((s) => (
                              <TableHead key={s}>{s}</TableHead>
                            ))}
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {boxes.map((b) => (
                            <TableRow key={b.id}>
                              <TableCell>
                                {b.label}
                                <small className="block-sub">{b.username || "待完善账号"}</small>
                                <small className="block-sub">
                                  {b.host ? `${b.host}:${b.port} · ${b.tls.toUpperCase()}` : "旧版服务器配置"}
                                </small>
                              </TableCell>
                              <TableCell>{b.all_folders ? "所有文件夹" : "仅收件箱"}<small className="block-sub">自 {b.since}</small></TableCell>
                              <TableCell>{timestamp(b.last_sync)}</TableCell>
                              <TableCell>
                                <Status
                                  state={b.error ? "review" : b.enabled ? "completed" : "open"}
                                  text={b.error ? "同步异常" : b.enabled ? "已启用" : "已停用"}
                                />
                                {b.error && <small className="block-sub">{b.error}</small>}
                              </TableCell>
                              <TableCell>
                                <div className="table-actions">
                                  <Button variant="ghost" onClick={() => setModal({ kind: "mailbox", mailbox: b })}>
                                    编辑
                                  </Button>
                                  {b.credential_configured && (
                                    <Button
                                      variant="ghost"
                                      onClick={async () => {
                                        try {
                                          const result = await post<{ folders: string[] }>(`${base}/mailboxes/${b.id}/test`);
                                          setFeedback(`连接成功，可读取 ${result.folders.length} 个文件夹。`);
                                        } catch (error) {
                                          setFeedback((error as Error).message);
                                        }
                                      }}
                                    >
                                      测试连接
                                    </Button>
                                  )}
                                  <Button
                                    variant="ghost"
                                    onClick={async () => {
                                      try {
                                        await put(`${base}/mailboxes/${b.id}`, {
                                          label: b.label,
                                          host: b.host,
                                          port: b.port,
                                          tls: b.tls,
                                          username: b.username,
                                          password: null,
                                          since: b.since,
                                          all_folders: b.all_folders,
                                          send_id: b.send_id,
                                          enabled: !b.enabled,
                                        });
                                        setFeedback(b.enabled ? "邮箱已停用，历史归档仍保留。" : "邮箱已启用。");
                                        refresh();
                                      } catch (error) {
                                        setFeedback((error as Error).message);
                                      }
                                    }}
                                  >
                                    {b.enabled ? "停用" : "启用"}
                                  </Button>
                                </div>
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    ) : (
                      <Empty
                        title="未登记邮箱"
                        text="点击“登记邮箱”，填写服务器和客户端授权码；测试成功后开始只读同步。"
                      />
                    )}
                  </section>
                  <div className="callout">
                    <ShieldCheck size={19} />
                    <div>
                      <strong>管理权限，不等于业务操作权限。</strong>
                      <p>
                        创建产品、上传和日常补录需运营权限；异常由当前牌照成员共享处理。管理员拥有本牌照全部页面与操作权限；跨牌照关联和密码重置由部署工具完成。
                      </p>
                    </div>
                  </div>
                </>
              )}
            </>
          )}
          <footer className="live-footer">
            <span>序川 · 基金运营工作台</span>
            <span>可独立部署 / 数据保留在本系统</span>
          </footer>
        </main>
      </div>
      {feedback && (
        <div className="toast" role="status">
          {feedback}
          <button aria-label="关闭提示" onClick={() => setFeedback("")}>
            <X size={14} />
          </button>
        </div>
      )}
      <Dialog
        open={!!modal}
        onOpenChange={(open) => {
          if (!open) setModal(null);
        }}
      >
        <DialogContent className={`live-dialog ${modal?.kind === "mail-detail" ? "mail-detail-dialog" : ""}`}>
          <DialogHeader>
            <DialogTitle>
              {
                {
                  product: "产品建档",
                  filing: "新建产品备案",
                  nav: modal?.kind === "nav" && modal.task ? "人工补齐材料" : "人工补录净值",
                  "nav-export": "导出产品净值",
                  upload: modal?.kind === "upload" && modal.productId
                    ? "上传到产品"
                    : modal?.kind === "upload" && modal.investorId
                      ? "上传到投资者"
                      : "上传资料",
                  material: "整理资料",
                  investor: modal?.kind === "investor" && modal.investor ? "整理投资者" : "建立投资者",
                  "bank-account": modal?.kind === "bank-account" && modal.account ? "编辑银行账户" : "新增银行账户",
                  "share-event": "整理份额信息",
                  "position-snapshot": "登记持仓快照",
                  "share-event-status": modal?.kind === "share-event-status"
                    ? { confirmed: "确认份额入账", archived: "仅归档份额信息", void: "作废份额信息" }[modal.status]
                    : "处理份额信息",
                  schedule: "应收配置",
                  lifecycle: "产品生命周期",
                  member: "成员授权",
                  task: "异常详情",
                  "task-mail-disposition": modal?.kind === "task-mail-disposition"
                    ? { notification: "设为仅作通知", duplicate: "标记重复邮件", void: "标记误发或作废" }[modal.disposition]
                    : "处理邮件异常",
                  mailbox: modal?.kind === "mailbox" && modal.mailbox ? "编辑邮箱" : "登记邮箱",
                  "mail-action": "处理邮件待办",
                  "mail-classify": "确认邮件分类",
                  "mail-detail": "邮件详情",
                  check: "检查应收材料",
                  share: "新增份额类别",
                  password: "修改登录密码",
                  rules: "净值校验阈值",
                }[modal?.kind || "product"]
              }
            </DialogTitle>
            <DialogDescription>
              {modal?.kind === "mail-detail"
                ? "完整正文与附件 · HTML 隔离展示并提供纯文本备用"
                : `${manager?.name || "账号设置"} · 所有操作均会留痕`}
            </DialogDescription>
          </DialogHeader>
          {modal?.kind === "mail-detail" && (
            <MailDetailView key={modal.item.id} item={modal.item} canDownload={Boolean(perm?.download)} />
          )}
          {modal?.kind === "product" && (
            <ProductForm
              managerId={managerId}
              candidate={modal.candidate}
              documentId={modal.documentId}
              done={done}
            />
          )}
          {modal?.kind === "filing" && (
            <ProductForm managerId={managerId} filing done={done} />
          )}
          {modal?.kind === "nav" && (
            <NavForm managerId={managerId} products={products} task={modal.task} suggestedDate={suggestedDate} done={done} />
          )}
          {modal?.kind === "nav-export" && (
            <NavExportForm
              managerId={managerId}
              products={products}
              initialProductId={modal.productId}
              suggestedDate={share?.latest?.valuation_date || suggestedDate}
              done={() => {
                setModal(null);
                setFeedback("Excel 已生成并开始下载。");
              }}
            />
          )}
          {modal?.kind === "upload" && (
            <UploadForm
              managerId={managerId}
              products={products}
              investors={investors}
              initialProductId={modal.productId}
              initialInvestorId={modal.investorId}
              done={done}
            />
          )}
          {modal?.kind === "material" && (
            <MaterialForm document={modal.document} products={products} investors={investors} done={done} />
          )}
          {modal?.kind === "investor" && (
            <InvestorForm managerId={managerId} investor={modal.investor} products={products} documents={docs} done={done} />
          )}
          {modal?.kind === "bank-account" && (
            <InvestorBankAccountForm investor={modal.investor} account={modal.account} products={products} documents={docs} done={done} />
          )}
          {modal?.kind === "share-event" && (
            <InvestorShareEventForm investor={modal.investor} investors={investors} products={products} sourceMail={modal.sourceMail} done={done} />
          )}
          {modal?.kind === "position-snapshot" && (
            <InvestorPositionSnapshotForm investor={modal.investor} investors={investors} products={products} sourceMail={modal.sourceMail} done={done} />
          )}
          {modal?.kind === "share-event-status" && (
            <ActionForm
              done={done}
              label={{ confirmed: "确认入账", archived: "仅归档", void: "确认作废" }[modal.status]}
              submit={(form) => put(`/investor-share-events/${modal.event.id}/status`, {
                revision: modal.event.revision,
                status: modal.status,
                reason: val(form, "reason"),
              })}
            >
              <p className="inline-note">
                <strong>{modal.event.product_name} · {modal.event.share_name || "未细分份额"}</strong><br />
                {modal.status === "confirmed"
                  ? "确认后，这条份额变动将计入持仓汇总。"
                  : modal.status === "archived"
                    ? "记录和来源依据会保留，但不会计入持仓。"
                    : "记录会标记作废，原始邮件和附件仍然保留。"}
              </p>
              <Field label="处理依据"><textarea name="reason" required maxLength={2000} rows={4} /></Field>
            </ActionForm>
          )}
          {modal?.kind === "schedule" && <ScheduleForm product={modal.product} done={done} />}
          {modal?.kind === "lifecycle" && <LifecycleForm product={modal.product} done={done} />}
          {modal?.kind === "member" && (
            <MemberForm
              managerId={managerId}
              member={modal.member}
              products={products}
              done={() => {
                done();
                void refreshMe();
              }}
            />
          )}
          {modal?.kind === "share" && (
            <ActionForm
              done={done}
              submit={(f) => post(`/products/${modal.product.id}/shares`, { name: val(f, "name") })}
            >
              <Field label="份额名称" hint="请与托管材料中的名称保持一致">
                <Input name="name" required maxLength={80} />
              </Field>
            </ActionForm>
          )}
          {modal?.kind === "check" && (
            <ActionForm
              done={done}
              label="检查所选估值日"
              submit={(f) => post(`${base}/check-missing?valuation_date=${val(f, "date")}`)}
            >
              <Field label="应收材料对应的估值日">
                <Input name="date" type="date" required defaultValue={suggestedDate} />
              </Field>
              <p className="inline-note">
                按交易日历检查指定估值日，下一交易日为应收日；日频 15:00 截止，当前覆盖 2025–2026 年。历史检查按当前产品配置，请先核对适用范围。
              </p>
            </ActionForm>
          )}
          {modal?.kind === "mailbox" && (
            <ActionForm
              done={done}
              label={modal.mailbox ? "测试并保存" : "测试、保存并启用"}
              submit={(f) => {
                const payload = {
                  label: val(f, "label"),
                  host: val(f, "host"),
                  port: Number(val(f, "port")),
                  tls: val(f, "tls"),
                  username: val(f, "username"),
                  password: String(f.get("password") || "") || null,
                  since: val(f, "since"),
                  all_folders: f.get("all_folders") === "on",
                  send_id: f.get("send_id") === "on",
                  enabled: f.get("enabled") === "on",
                };
                return modal.mailbox
                  ? put(`${base}/mailboxes/${modal.mailbox.id}`, payload)
                  : post(`${base}/mailboxes`, { ...payload, password: String(f.get("password")) });
              }}
            >
              <Field label="邮箱名称">
                <Input name="label" required maxLength={100} defaultValue={modal.mailbox?.label} placeholder="例如：吉余运营邮箱" />
              </Field>
              <div className="field-pair">
                <Field label="IMAP 服务器">
                  <Input name="host" required maxLength={253} defaultValue={modal.mailbox?.host || "imap.163.com"} />
                </Field>
                <Field label="端口">
                  <Input name="port" type="number" required min={1} max={65535} defaultValue={modal.mailbox?.port || 993} />
                </Field>
              </div>
              <Field label="加密方式">
                <select name="tls" defaultValue={modal.mailbox?.tls || "ssl"}>
                  <option value="ssl">SSL/TLS（通常端口 993）</option>
                  <option value="starttls">STARTTLS（通常端口 143）</option>
                </select>
              </Field>
              <Field label="邮箱账号">
                <Input name="username" type="email" required maxLength={254} autoComplete="off" defaultValue={modal.mailbox?.username} />
              </Field>
              <Field
                label={modal.mailbox ? "客户端授权码（留空表示不更换）" : "客户端授权码"}
                hint="不是网页登录密码；保存后不会再显示。"
              >
                <Input name="password" type="password" required={!modal.mailbox} maxLength={512} autoComplete="new-password" />
              </Field>
              <Field label="从哪一天开始同步">
                <Input name="since" type="date" required defaultValue={modal.mailbox?.since || "2000-01-01"} />
              </Field>
              <label className="check-line">
                <input name="all_folders" type="checkbox" defaultChecked={modal.mailbox?.all_folders ?? true} />
                同步全部业务文件夹（自动排除已发送、草稿、垃圾邮件和已删除）
              </label>
              <label className="check-line">
                <input name="send_id" type="checkbox" defaultChecked={modal.mailbox?.send_id ?? modal.mailbox?.host?.endsWith("163.com") ?? true} />
                登录后发送客户端标识（163 邮箱建议开启）
              </label>
              <label className="check-line">
                <input name="enabled" type="checkbox" defaultChecked={modal.mailbox?.enabled ?? true} />
                保存后启用后台只读同步
              </label>
              <p className="inline-note">保存前会测试连接。系统使用只读 IMAP，不设置已读、不移动或删除邮件；不同邮箱独立同步。</p>
            </ActionForm>
          )}
          {modal?.kind === "mail-action" && modal.item.action && (
            <ActionForm
              done={done}
              label="记录处理完成"
              submit={(f) =>
                post(`/mail-actions/${modal.item.action!.id}/complete`, {
                  revision: modal.item.action!.revision,
                  reason: val(f, "reason"),
                })
              }
            >
              <p className="inline-note">
                <strong>{modal.item.action.suggested_action}</strong>
                <br />
                {modal.item.title}
              </p>
              <Field label="处理结果" hint="填写实际完成的动作或核查结论，将与邮件原件一同留痕。">
                <textarea name="reason" required maxLength={2000} rows={5} />
              </Field>
              {perm?.download && (
                <a className="text-link" href={`/api/documents/${modal.item.document_id}/download`}>
                  先查看邮件原件
                </a>
              )}
            </ActionForm>
          )}
          {modal?.kind === "mail-classify" && (
            <ActionForm
              done={done}
              label="保存分类"
              submit={(f) =>
                put(`/mail-items/${modal.item.id}/classification`, {
                  revision: modal.item.revision,
                  category: val(f, "category"),
                  handling_mode: val(f, "handling_mode"),
                  suggested_action: val(f, "suggested_action") || null,
                })
              }
            >
              <p className="inline-note">{modal.item.title}</p>
              <Field label="邮件类型">
                <select name="category" defaultValue="other">
                  <option value="nav_valuation">净值 / 估值</option>
                  <option value="futures_settlement">期货结算</option>
                  <option value="reconciliation_data">对账 / 数据包</option>
                  <option value="risk_monitoring">风险 / 投监</option>
                  <option value="contract_seal">合同 / 用印</option>
                  <option value="investor_redemption">申赎 / 投资者</option>
                  <option value="security">安全提醒</option>
                  <option value="action_required">业务待办</option>
                  <option value="completion_receipt">完成通知</option>
                  <option value="marketing">营销信息</option>
                  <option value="other">其他</option>
                </select>
              </Field>
              <Field label="处理方式">
                <select name="handling_mode" defaultValue="receipt">
                  <option value="receipt">作为接收记录</option>
                  <option value="task">生成业务待办</option>
                  <option value="archive">仅归档</option>
                </select>
              </Field>
              <Field label="待办建议（选择生成待办时填写）">
                <Input name="suggested_action" maxLength={500} placeholder="例如：核对并回复托管通知" />
              </Field>
              <p className="inline-note">选择净值 / 估值后，受支持的附件才会进入净值解析。</p>
            </ActionForm>
          )}
          {modal?.kind === "task-mail-disposition" && (
            <ActionForm
              done={done}
              label="确认处理"
              submit={(form) =>
                post(`/tasks/${modal.task.id}/mail-disposition`, {
                  revision: modal.task.revision,
                  disposition: modal.disposition,
                  reason: val(form, "reason"),
                })
              }
            >
              <p className="inline-note">
                {{
                  notification: "邮件将改为仅归档，停止未完成的解析并关闭关联的解析异常。",
                  duplicate: "本次邮件将标记为重复，停止未完成的解析；已有有效业务数据不会被覆盖。",
                  void: "本次邮件将标记为误发或作废，不再参与后续解析。",
                }[modal.disposition]}
                邮件原件和附件仍会完整保留。
              </p>
              <Field label="处理依据" hint="说明判断依据，处理结论会写入业务留痕。">
                <textarea name="reason" required maxLength={2000} rows={5} />
              </Field>
            </ActionForm>
          )}
          {modal?.kind === "rules" && (
            <ActionForm
              done={done}
              submit={(f) => put(`${base}/rules`, { max_nav_change: val(f, "threshold") || null })}
            >
              <Field label="单位净值变化比率阈值" hint="输入 0.05 表示 5%；留空停用此条异常提醒。">
                <Input
                  name="threshold"
                  inputMode="decimal"
                  defaultValue={rulesState.data?.max_nav_change || ""}
                />
              </Field>
              <p className="inline-note">
                超过阈值会进入异常队列，运营人员填写原因后可接受真实波动。此规则不替代强制完整性校验，不回溯改动已确认历史。
              </p>
            </ActionForm>
          )}
          {modal?.kind === "password" && (
            <ActionForm
              label="修改并重新登录"
              done={() => void refreshMe()}
              submit={(f) =>
                post("/auth/password", {
                  old_password: String(f.get("old_password")),
                  new_password: String(f.get("new_password")),
                })
              }
            >
              <Field label="当前密码">
                <Input
                  name="old_password"
                  type="password"
                  required
                  autoComplete="current-password"
                />
              </Field>
              <Field label="新密码（12–128 位）">
                <Input
                  name="new_password"
                  type="password"
                  required
                  minLength={12}
                  maxLength={128}
                  autoComplete="new-password"
                />
              </Field>
            </ActionForm>
          )}
          {modal?.kind === "task" && manager && (
            <TaskDetail
              key={modal.task.id + modal.task.revision}
              task={tasks.find((t) => t.id === modal.task.id) || modal.task}
              manager={manager}
              documents={docs}
              done={done}
              onComplete={(task) => setModal({ kind: "nav", task })}
              onUpload={() => setModal({ kind: "upload" })}
              onOpenMail={openOriginalMail}
              onMailDisposition={(task, disposition) =>
                setModal({ kind: "task-mail-disposition", task, disposition })
              }
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function TaskDetail({
  task,
  manager,
  done,
  onComplete,
  onUpload,
  onOpenMail,
  onMailDisposition,
  documents,
}: {
  documents: Doc[];
  task: Task;
  manager: Manager;
  done: () => void;
  onComplete: (t: Task) => void;
  onUpload: () => void;
  onOpenMail: (itemId: string) => void;
  onMailDisposition: (task: Task, disposition: "notification" | "duplicate" | "void") => void;
}) {
  const [error, setError] = useState(""),
    [selected, setSelected] = useState(""),
    [reversal, setReversal] = useState(false);
  const canProcess = manager.permissions.member,
    canWrite = manager.permissions.write;
  return (
    <div className="task-detail">
      <div className="task-context">
        <Status state={task.status} />
        <strong>{taskLabel(task.kind)}</strong>
        <span>
          {task.product_name} · {task.valuation_date || "待核对日期"}
        </span>
        <small>当前牌照成员均可直接处理，提交时记录实际账号。</small>
      </div>
      <ErrorNote error={error} />
      {task.payload.errors?.map((e, i) => (
        <p key={i} className="parse-error">
          {e.reason || e.message}
        </p>
      ))}
      {task.payload.error && <p className="parse-error">{task.payload.error}</p>}
      {task.payload.message && <p className="parse-error">{task.payload.message}</p>}
      {task.mail_item_id && manager.permissions.archive &&
        (task.mail_item_category !== "investor_redemption" || manager.permissions.investor_read) && (
          <Button variant="outline" onClick={() => onOpenMail(task.mail_item_id!)}>
            <Mail />
            查看原始邮件
          </Button>
        )}
      {task.status !== "resolved" && task.kind !== "investor_share" && task.mail_item_id && canWrite &&
        (task.mail_item_category !== "investor_redemption" || manager.permissions.investor_write) && (
          <div className="mail-disposition-actions">
            <span>这封邮件无需继续形成异常时：</span>
            <div className="row-actions">
              <Button variant="outline" onClick={() => onMailDisposition(task, "notification")}>仅作通知</Button>
              <Button variant="outline" onClick={() => onMailDisposition(task, "duplicate")}>重复邮件</Button>
              <Button variant="outline" onClick={() => onMailDisposition(task, "void")}>误发 / 作废</Button>
            </div>
          </div>
        )}
      {task.payload.document_id && manager.permissions.download && (
        <a className="text-link" href={`/api/documents/${task.payload.document_id}/download`}>
          下载原始材料核对
        </a>
      )}
      {task.status === "resolved" ? (
        <>
          <p className="inline-note">此事项已经解决，原始依据和处理结论保留。</p>
          <pre>{JSON.stringify(task.resolution, null, 2)}</pre>
        </>
      ) : (
        <>
          {(task.kind === "conflict" || task.kind === "validation") && (
            <>
              <div className="candidate-list">
                {task.candidates.map((r) => (
                  <label
                    key={r.id}
                    className={"candidate-card " + (selected === r.id ? "selected" : "")}
                  >
                    <input
                      name="candidate"
                      type="radio"
                      value={r.id}
                      checked={selected === r.id}
                      onChange={() => setSelected(r.id)}
                      disabled={!canProcess}
                    />
                    <div>
                      <span className="candidate-nav">{number(r.unit_nav, 6)}</span>
                      <small>
                        {sourceLabel(r.source)} · {timestamp(r.received_at)}
                      </small>
                      <small>
                        规模 {number(r.net_assets, 2)} 元 / 总份额 {number(r.total_shares, 4)}
                      </small>
                      {r.validation.map((v) => (
                        <p className="parse-error" key={v.rule}>
                          {v.message}
                          {!v.overridable ? "（不可豁免）" : ""}
                        </p>
                      ))}
                    </div>
                  </label>
                ))}
              </div>
              {canProcess && (
                <ActionForm
                  done={done}
                  label="确认有效版本"
                  disabled={!selected}
                  submit={(f) =>
                    post(`/tasks/${task.id}/resolve`, {
                      revision: task.revision,
                      record_id: selected,
                      reversal,
                      reason: val(f, "reason"),
                    })
                  }
                >
                  <label className="check-line">
                    <input
                      type="checkbox"
                      checked={reversal}
                      onChange={(e) => setReversal(e.target.checked)}
                    />
                    将本次确认标注为反账后
                  </label>
                  <Field label={reversal ? "反账原因（必填）" : "处理说明"}>
                    <textarea
                      name="reason"
                      rows={3}
                      maxLength={2000}
                      required={reversal || task.kind === "validation"}
                    />
                  </Field>
                  <p className="inline-note">
                    确认后，该估值日按选定版本展示并计算曲线；原记录不覆盖。收到时间保留为实际材料收到日期。
                  </p>
                </ActionForm>
              )}
            </>
          )}
          {task.kind === "investor_share" && (
            <div className="investor-share-task">
              <div className="investor-share-task-grid">
                <div><span>投资者</span><strong>{task.investor_name || "待识别"}</strong></div>
                <div><span>产品</span><strong>{task.product_name}</strong></div>
                <div><span>异常原因</span><strong>{task.payload.reason === "position_difference" ? "托管快照差异" : task.payload.missing_mail ? "缺少邮件依据" : "确认字段不完整"}</strong></div>
                <div><span>业务日期</span><strong>{task.valuation_date || task.payload.as_of_date || "待补充"}</strong></div>
              </div>
              {task.investor_share_event && (
                <div className="investor-share-task-record">
                  <strong>{shareEventLabels[task.investor_share_event.event_type]} · {task.investor_share_event.share_name || "总份额"}</strong>
                  <span>份额变动 {task.investor_share_event.units_delta === null ? "未提供" : number(task.investor_share_event.units_delta)}</span>
                  <span>确认后份额 {task.investor_share_event.balance_after === null ? "未提供" : number(task.investor_share_event.balance_after)}</span>
                </div>
              )}
              {task.investor_position_snapshot && (
                <div className="investor-share-task-record">
                  <strong>托管快照 · {task.investor_position_snapshot.share_name || "总份额"}</strong>
                  <span>托管份额 {number(task.investor_position_snapshot.units)}</span>
                  <span>差异 {number(task.payload.difference)}</span>
                </div>
              )}
              {task.investor_share_event?.status === "pending" && manager.permissions.investor_write && (
                <ActionForm
                  label="保存处理结论"
                  done={done}
                  submit={(form) => put(`/investor-share-events/${task.investor_share_event!.id}/status`, {
                    revision: task.investor_share_event!.revision,
                    status: val(form, "status"),
                    reason: val(form, "reason"),
                  })}
                >
                  <Field label="处理方式">
                    <select name="status" defaultValue="archived">
                      <option value="archived">仅保留来源，不计入份额</option>
                      <option value="void">误发或错误记录，作废</option>
                    </select>
                  </Field>
                  <Field label="处理说明"><textarea name="reason" required maxLength={2000} /></Field>
                  <p className="inline-note">需要计入份额时，请从原始邮件重新整理完整记录；旧记录和本次结论都会保留。</p>
                </ActionForm>
              )}
              {task.investor_position_snapshot && (
                <p className="inline-note">收到更新后的托管快照并登记后，旧差异会自动关闭；当前记录不会被直接改写。</p>
              )}
            </div>
          )}
          {canProcess && ["parse", "validation"].includes(task.kind) && (
            <div className="row-actions">
              <Button variant="outline" onClick={() => onComplete(task)}>
                人工补齐并核对材料
              </Button>
              {task.payload.document_id && (
                <Button
                  variant="ghost"
                  onClick={async () => {
                    try {
                      await post(`/documents/${task.payload.document_id}/reparse`);
                      done();
                    } catch (e) {
                      setError((e as Error).message);
                    }
                  }}
                >
                  重新解析
                </Button>
              )}
            </div>
          )}
          {task.kind === "missing" && (
            <>
              <p className="inline-note">
                应收日 {task.payload.due_date || "待核对"}，截止 {task.payload.cutoff || "15:00"}。
                {task.payload.stage === "followup" ? "已跨交易日仍未收到，请核查并按需在托管平台补发。" : "已超过接收截止时间。"}
                材料匹配后解除缺件；解析和校验异常继续保留。
              </p>
              {task.payload.last_resend && <p className="inline-note">最近托管补发：{timestamp(task.payload.last_resend.at)} · {task.payload.last_resend.reason}。仍在等待材料。</p>}
              {canProcess && <ActionForm label="记录已在托管平台补发" done={done} submit={f => post(`/tasks/${task.id}/custodian-resend`, {revision: task.revision, reason: val(f, "reason")})}>
                <Field label="补发操作说明"><textarea name="reason" required maxLength={2000} placeholder="记录已完成的托管平台操作或回执信息" /></Field>
                <p className="inline-note">只记录你已完成的补发操作，不会替你发送邮件，也不会关闭缺件。</p>
              </ActionForm>}
              {manager.permissions.archive && <ActionForm label="确认对应净值材料已收到" done={done} disabled={!documents.some(d => !d.filename.toLowerCase().endsWith(".eml"))} submit={f => post(`/tasks/${task.id}/material-received`, {revision: task.revision, document_id: val(f, "document_id"), reason: val(f, "reason")})}>
                <Field label="已核对的净值附件"><select name="document_id" required defaultValue=""><option value="" disabled>请选择归档附件</option>{documents.filter(d => !d.filename.toLowerCase().endsWith(".eml") && (!d.product_id || d.product_id === task.product_id)).map(d => <option key={d.id} value={d.id}>{d.filename} · {timestamp(d.received_at)}</option>)}</select></Field>
                <Field label="材料对应关系说明"><textarea name="reason" required maxLength={2000} placeholder="确认材料对应本事项的产品、份额和估值日" /></Field>
                <p className="inline-note">适用于原件已到但解析未成功；仅解除缺件，不自动确认净值，不关闭解析异常。</p>
              </ActionForm>}
              {canWrite && (
                <Button onClick={onUpload}>
                  <Upload />
                  上传补充材料
                </Button>
              )}
            </>
          )}
          {task.kind === "mailbox" && (
            <p className="inline-note">
              需部署管理员检查服务器配置或网络。邮箱同步恢复后自动解决，不能手动忽略。
            </p>
          )}
        </>
      )}
    </div>
  );
}
