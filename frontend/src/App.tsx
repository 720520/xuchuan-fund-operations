import { useEffect, useState, type ReactNode } from "react";
import {
  Activity,
  ArrowRight,
  Building2,
  ChartNoAxesCombined,
  Check,
  ChevronRight,
  CircleAlert,
  ClipboardList,
  Download,
  FileText,
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
  previousFriday,
  previousWeekday,
  sourceLabel,
  stageLabel,
  taskLabel,
  timestamp,
  type Audit,
  type Candidate,
  type Doc,
  type History,
  type Mailbox,
  type Manager,
  type Me,
  type Member,
  type Product,
  type ProductFiling,
  type Task,
} from "./api";
import {
  ActionForm,
  Field,
  LifecycleForm,
  MemberForm,
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
  { id: "mail", label: "邮件归档", icon: Mail },
  { id: "exceptions", label: "异常中心", icon: CircleAlert },
  { id: "upload", label: "上传与解析", icon: Upload },
  { id: "audit", label: "业务留痕", icon: ClipboardList },
  { id: "settings", label: "组织与权限", icon: Settings2 },
];
type Modal =
  | { kind: "product"; candidate?: Candidate; documentId?: string }
  | { kind: "filing" }
  | { kind: "nav"; task?: Task }
  | { kind: "upload" }
  | { kind: "schedule"; product: Product }
  | { kind: "lifecycle"; product: Product }
  | { kind: "member"; member?: Member }
  | { kind: "task"; task: Task }
  | { kind: "mailbox"; mailbox?: Mailbox }
  | { kind: "check" }
  | { kind: "share"; product: Product }
  | { kind: "password" }
  | { kind: "rules" };

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
    [modal, setModal] = useState<Modal | null>(null),
    [feedback, setFeedback] = useState(""),
    [search, setSearch] = useState(""),
    [showHiddenProducts, setShowHiddenProducts] = useState(false),
    [selectedProduct, setSelectedProduct] = useState(""),
    [selectedShare, setSelectedShare] = useState(""),
    [period, setPeriod] = useState("all");
  const [checkDate, setCheckDate] = useState(previousWeekday());
  const manager = me.managers.find((m) => m.id === managerId),
    perm = manager?.permissions;
  const base = manager ? `/managers/${manager.id}` : null;
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
  const summaryState = useResource<{
    expected: number;
    received: number;
    confirmed: number;
    processed_today: number | null;
    archived: number | null;
  }>(base && perm?.read ? base + `/summary?valuation_date=${checkDate}` : null, revision);
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
    setMobile(false);
    setSearch("");
  }
  const visibleNav = navigation
    .filter((n) => !["mail", "upload"].includes(n.id) || perm?.archive)
    .filter((n) => n.id !== "exceptions" || perm?.member)
    .filter((n) => n.id !== "settings" || perm?.admin)
    .filter((n) => n.id !== "audit" || perm?.archive || perm?.admin);
  const pending = tasks.filter((t) => t.status !== "resolved");
  const pendingProducts = Array.from(
    new Map(
      docs.flatMap((document) =>
        (document.job?.result.errors || [])
          .filter((error) => error.candidate)
          .map((error) => {
            const candidate = error.candidate!;
            return [
              `${document.id}:${candidate.product_code || candidate.product_name || "unknown"}`,
              { document, candidate },
            ] as const;
          }),
      ),
    ).values(),
  );
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
    <div className={"app-shell " + (mobile ? "menu-open" : "")}>
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
        <div className="workspace">
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
              onClick={() => go(n.id)}
              aria-current={view === n.id ? "page" : undefined}
            >
              <n.icon size={17} />
              {n.label}
              {n.id === "exceptions" && pending.length > 0 && (
                <span className="nav-count">{pending.length}</span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="sync-note">
            <i />
            业务数据每 15 秒刷新
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
                        value={checkDate}
                        onChange={(e) => {
                          if (e.target.value) setCheckDate(e.target.value);
                        }}
                      />
                    </label>
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
                      {summaryState.data?.confirmed ?? 0}。周频与节假日请按材料核实日期。
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
                          {pendingProducts.map(({ document, candidate }) => (
                            <TableRow key={`${document.id}:${candidate.product_code || candidate.product_name}`}>
                              <TableCell>
                                <strong>{candidate.product_name || "名称待核对"}</strong>
                                <small className="block-sub">{candidate.product_code || "代码待核对"}</small>
                              </TableCell>
                              <TableCell>{candidate.share_class || "待核对"}</TableCell>
                              <TableCell>
                                {sourceLabel(document.source)}
                                <small className="block-sub">{document.filename}</small>
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
                                <TableCell>{p.cutoff}</TableCell>
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
                    title={view === "mail" ? "邮件归档" : "上传与解析"}
                    text={
                      view === "mail"
                        ? "原始邮件不删除，附件与业务记录相互关联。"
                        : "上传后先保留原件，再由后台解析与规则校验。"
                    }
                  >
                    {perm?.write && (
                      <Button onClick={() => setModal({ kind: "upload" })}>
                        <Upload />
                        上传附件
                      </Button>
                    )}
                  </PageTitle>
                  <ErrorNote error={docsState.error} />
                  {view === "mail" && (
                    <div className="mailbox-summary">
                      {boxes.length ? (
                        boxes.map((b) => (
                          <section className="panel" key={b.id}>
                            <Mail size={19} />
                            <h2>{b.label}</h2>
                            <Status
                              state={b.error ? "review" : b.enabled ? "completed" : "open"}
                              text={b.error ? "连接异常" : b.enabled ? "已启用" : "待配置启用"}
                            />
                            <p>上次同步：{timestamp(b.last_sync)}</p>
                            {b.error && <ErrorNote error={b.error} />}
                          </section>
                        ))
                      ) : (
                        <div className="callout compact-callout">
                          <Mail size={19} />
                          <span>
                            尚未接入邮箱。管理员可在“组织与权限”中填写配置并测试启用。
                          </span>
                        </div>
                      )}
                    </div>
                  )}
                  <section className="panel">
                    <div className="list-tools">
                      <div className="search-inline">
                        <Search size={15} />
                        <Input
                          aria-label="搜索归档文件"
                          placeholder="搜索文件名称、邮件主题"
                          value={search}
                          onChange={(e) => setSearch(e.target.value)}
                        />
                      </div>
                      <span className="muted">最近 300 份材料</span>
                    </div>
                    {docs.length ? (
                      <Table>
                        <TableHeader>
                          <TableRow>
                            {["材料 / 邮件", "来源", "收到时间", "解析状态", "操作"].map((s) => (
                              <TableHead key={s}>{s}</TableHead>
                            ))}
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {docs
                            .filter(
                              (d) =>
                                (view !== "mail" || d.source === "email") &&
                                (d.filename + (d.metadata_json.subject || "")).includes(search),
                            )
                            .map((d) => (
                              <TableRow key={d.id}>
                                <TableCell>
                                  <div className="file-identity">
                                    <FileText size={19} />
                                    <div>
                                      <strong>{d.metadata_json.subject || d.filename}</strong>
                                      <small className="block-sub">
                                        {d.metadata_json.from || d.filename} ·{" "}
                                        {(d.size / 1024).toFixed(1)} KB
                                      </small>
                                      <small className="hash" title={d.sha256}>
                                        SHA-256 {d.sha256.slice(0, 16)}…
                                      </small>
                                    </div>
                                  </div>
                                  {d.job?.result.errors?.slice(0, 2).map((e, i) => (
                                    <small key={i} className="parse-error">
                                      {e.reason}
                                    </small>
                                  ))}
                                </TableCell>
                                <TableCell>
                                  {sourceLabel(d.source)}
                                  {d.parent_id && <small className="block-sub">邮件附件</small>}
                                </TableCell>
                                <TableCell>{timestamp(d.received_at)}</TableCell>
                                <TableCell>
                                  <Status
                                    state={d.job?.status || "completed"}
                                    text={d.job ? undefined : "原件已归档"}
                                  />
                                  {d.job?.status === "queued" && (
                                    <small className="block-sub">等待后台任务</small>
                                  )}
                                </TableCell>
                                <TableCell>
                                  <div className="row-actions">
                                    {perm?.download && (
                                      <a
                                        className="icon-link"
                                        aria-label={`下载 ${d.filename}`}
                                        href={`/api/documents/${d.id}/download`}
                                      >
                                        <Download size={15} />
                                      </a>
                                    )}
                                    {perm?.write &&
                                      d.job &&
                                      !["queued", "processing"].includes(d.job.status) && (
                                        <Button
                                          variant="ghost"
                                          onClick={() =>
                                            void action(() => post(`/documents/${d.id}/reparse`))
                                          }
                                        >
                                          重新解析
                                        </Button>
                                      )}
                                    {perm?.write &&
                                      d.job?.result.errors?.find((e) => e.candidate) && (
                                        <Button
                                          variant="outline"
                                          onClick={() =>
                                            setModal({
                                              kind: "product",
                                              candidate: d.job!.result.errors!.find(
                                                (e) => e.candidate,
                                              )!.candidate,
                                              documentId: d.id,
                                            })
                                          }
                                        >
                                          确认候选产品
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
                        title={docsState.loading ? "正在读取归档…" : "还没有归档材料"}
                        text="上传托管附件开始试运行；邮箱需由管理员配置后才能收件。"
                      >
                        {perm?.write && (
                          <Button variant="outline" onClick={() => setModal({ kind: "upload" })}>
                            <Upload />
                            上传第一份材料
                          </Button>
                        )}
                      </Empty>
                    )}
                    <div className="table-footer">
                      <span>原件仅追加 · 不提供删除或替换入口</span>
                      <span>查看与下载分别授权</span>
                    </div>
                  </section>
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
                                  <strong>{taskLabel(t.kind)}</strong>
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
                                  <Button
                                    variant="ghost"
                                    onClick={() => setModal({ kind: "task", task: t })}
                                  >
                                    查看与处理
                                    <ChevronRight size={13} />
                                  </Button>
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
        <DialogContent className="live-dialog">
          <DialogHeader>
            <DialogTitle>
              {
                {
                  product: "产品建档",
                  filing: "新建产品备案",
                  nav: modal?.kind === "nav" && modal.task ? "人工补齐材料" : "人工补录净值",
                  upload: "上传与解析",
                  schedule: "应收配置",
                  lifecycle: "产品生命周期",
                  member: "成员授权",
                  task: "异常详情",
                  mailbox: modal?.kind === "mailbox" && modal.mailbox ? "编辑邮箱" : "登记邮箱",
                  check: "检查应收材料",
                  share: "新增份额类别",
                  password: "修改登录密码",
                  rules: "净值校验阈值",
                }[modal?.kind || "product"]
              }
            </DialogTitle>
            <DialogDescription>{manager?.name || "账号设置"} · 所有操作均会留痕</DialogDescription>
          </DialogHeader>
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
            <NavForm managerId={managerId} products={products} task={modal.task} done={done} />
          )}
          {modal?.kind === "upload" && (
            <UploadForm managerId={managerId} products={products} done={done} />
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
                <Input name="date" type="date" required defaultValue={previousFriday()} />
              </Field>
              <p className="inline-note">
                仅检查管理员纳入应收且已过接收截止时间的产品。周频日期可手选；节假日日历尚未接入，请核实估值日。
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
                同步所有可读取文件夹（包括已归档、已发送等；跨文件夹同一原件只归档一次）
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
              done={done}
              onComplete={(task) => setModal({ kind: "nav", task })}
              onUpload={() => setModal({ kind: "upload" })}
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
}: {
  task: Task;
  manager: Manager;
  done: () => void;
  onComplete: (t: Task) => void;
  onUpload: () => void;
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
                收到匹配产品、份额和估值日的数据后自动解决；解析或校验异常另行保留。
              </p>
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
