import { useEffect, useState } from "react";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
export async function api<T = unknown>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch("/api" + path, {
    credentials: "same-origin",
    ...options,
    headers: {
      ...(options.body && !(options.body instanceof FormData)
        ? { "Content-Type": "application/json" }
        : {}),
      ...options.headers,
    },
  });
  const body = await response.json().catch(() => ({ detail: "响应内容不可读" }));
  if (!response.ok) {
    if (response.status === 401 && path !== "/auth/login")
      window.dispatchEvent(new Event("session-expired"));
    const detail = Array.isArray(body.detail)
      ? body.detail
          .map((x: { msg: string; loc: string[] }) => `${x.loc?.slice(1).join(".")}: ${x.msg}`)
          .join("；")
      : body.detail;
    throw new ApiError(detail || `请求失败 (${response.status})`, response.status);
  }
  return body as T;
}
export const post = <T = unknown>(path: string, body?: unknown) =>
  api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
export const put = <T = unknown>(path: string, body: unknown) =>
  api<T>(path, { method: "PUT", body: JSON.stringify(body) });

export async function downloadFile(path: string, fallbackName: string) {
  const response = await fetch("/api" + path, { credentials: "same-origin" });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "响应内容不可读" }));
    if (response.status === 401) window.dispatchEvent(new Event("session-expired"));
    const detail = Array.isArray(body.detail)
      ? body.detail
          .map((item: { msg?: string; loc?: string[] }) =>
            `${item.loc?.slice(1).join(".") || "参数"}: ${item.msg || "无效"}`,
          )
          .join("；")
      : body.detail;
    throw new ApiError(detail || `下载失败 (${response.status})`, response.status);
  }
  const disposition = response.headers.get("content-disposition") || "";
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  let filename = fallbackName;
  if (encoded) {
    try {
      filename = decodeURIComponent(encoded);
    } catch {
      filename = fallbackName;
    }
  }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

export function useResource<T>(path: string | null, revision: number) {
  const [state, setState] = useState<{
    path: string | null;
    data?: T;
    error?: string;
    loading: boolean;
  }>({ path, loading: true });
  useEffect(() => {
    if (!path) {
      setState({ path, loading: false });
      return;
    }
    const controller = new AbortController();
    setState((s) => ({ path, data: s.path === path ? s.data : undefined, loading: true }));
    api<T>(path, { signal: controller.signal })
      .then((data) => setState({ path, data, loading: false }))
      .catch((e) => {
        if (!controller.signal.aborted) setState({ path, error: e.message, loading: false });
      });
    return () => controller.abort();
  }, [path, revision]);
  return state.path === path ? state : { path, loading: true };
}

export type Permission = {
  member: boolean;
  read: boolean;
  write: boolean;
  admin: boolean;
  download: boolean;
  all_products: boolean;
  archive: boolean;
  investor_read: boolean;
  investor_write: boolean;
  roles: string[];
};
export type ProductFiling = {
  id: string;
  code: string;
  name: string;
  currency: string;
  strategy: string;
  shares: string[];
  status: "in_progress" | "completed";
  product_id: string | null;
  created_at: string;
  completed_at: string | null;
};
export type Manager = { id: string; name: string; group_id: string; permissions: Permission };
export type Me = { id: string; name: string; email: string; managers: Manager[] };
export type Nav = {
  id: string;
  product_id: string;
  share_id: string;
  valuation_date: string;
  unit_nav: string;
  accumulated_nav: string | null;
  net_assets: string | null;
  total_shares: string | null;
  source: string;
  received_at: string;
  document_id: string | null;
  actor_name?: string;
  actor_id: string | null;
  validation: { rule: string; message: string; overridable: boolean }[];
  reported_metrics: Record<string, string>;
  reversal?: boolean;
  effective?: boolean;
};
export type Share = { id: string; name: string; latest: Nav | null };
export type Product = {
  id: string;
  code: string;
  name: string;
  currency: string;
  strategy: string;
  expected: boolean;
  frequency: "daily" | "weekly" | "off";
  weekday: number;
  cutoff: string;
  lifecycle_status: "active" | "liquidating" | "liquidated" | "archived";
  lifecycle_date: string | null;
  lifecycle_reason: string | null;
  lifecycle_updated_at: string | null;
  lifecycle_updated_by: string | null;
  shares: Share[];
};
export type History = {
  effective: Nav[];
  versions: Nav[];
  series: { date: string; nav: string; nav_change: string; nav_drawdown: string }[];
  metric_basis: string;
};
export type Candidate = {
  product_code?: string;
  product_name?: string;
  share_class?: string;
  valuation_date?: string;
  unit_nav?: string;
};
export type Doc = {
  id: string;
  product_id: string | null;
  filename: string;
  sha256: string;
  size: number;
  source: string;
  received_at: string;
  parent_id: string | null;
  metadata_json: { subject?: string; from?: string; material_category?: string };
  category?: string | null;
  material_type?: string | null;
  title?: string | null;
  business_date?: string | null;
  period_start?: string | null;
  period_end?: string | null;
  notes?: string;
  sensitivity?: "standard" | "investor_sensitive";
  material_status?: "pending" | "organized";
  material_revision?: number;
  organized_at?: string | null;
  organized_by?: string | null;
  products?: { id: string; name: string }[];
  product_ids?: string[];
  investors?: { id: string; display_name: string; investor_type: string }[];
  investor_ids?: string[];
  job: null | {
    id: string;
    status: string;
    result: {
      errors?: { reason: string; candidate?: Candidate }[];
      record_ids?: string[];
      record_count?: number;
      parser_version?: string;
      skip_reason?: string;
    };
  };
};
export type DocPage = {
  items: Doc[];
  total: number;
  limit: number;
  offset: number;
  counts: {
    all: number;
    pending: number;
    linked: number;
    attention: number;
  };
};
export type InvestorBankAccount = {
  id: string;
  investor_id: string;
  account_name: string;
  account_number_masked: string;
  bank_name: string;
  branch_name: string;
  currency: string;
  status: "active" | "inactive";
  source_document_id?: string | null;
  product_ids: string[];
  revision: number;
  created_at: string;
  updated_at: string;
};
export type Investor = {
  id: string;
  manager_id: string;
  investor_type:
    | "individual"
    | "institution"
    | "fund_product"
    | "asset_management"
    | "manager_co_investment"
    | "other";
  display_name: string;
  status: "pending" | "confirmed" | "historical";
  source: "manual" | "directory_reference" | "material";
  notes: string;
  revision: number;
  created_at: string;
  updated_at: string;
  product_ids: string[];
  products: { id: string; name: string }[];
  material_count: number;
  suitability_class?: "ordinary" | "professional" | "unknown";
  professional_investor_type?: string | null;
  certificate_type?: string | null;
  certificate_number_masked?: string | null;
  certificate_valid_until?: string | null;
  nationality_or_region?: string | null;
  contact_email?: string | null;
  contact_phone?: string | null;
  specific_object_status?: string | null;
  specific_object_confirmed_at?: string | null;
  risk_level?: string | null;
  risk_assessed_at?: string | null;
  risk_expires_at?: string | null;
  qualified_material_status?: string | null;
  qualified_material_from?: string | null;
  qualified_material_until?: string | null;
  profile_source_document_id?: string | null;
  suitability_source_document_id?: string | null;
  bank_accounts?: InvestorBankAccount[];
};
export type Task = {
  id: string;
  kind: string;
  status: string;
  revision: number;
  assignee_id: string | null;
  assignee_name: string | null;
  product_id: string | null;
  product_name: string;
  share_id: string | null;
  valuation_date: string | null;
  created_at: string;
  payload: {
    expectation_id?: string;
    due_date?: string;
    cutoff?: string;
    followup_date?: string;
    followup_time?: string;
    stage?: string;
    last_resend?: { actor_id: string; at: string; reason: string };
    document_id?: string;
    errors?: { reason?: string; message?: string; candidate?: Candidate }[];
    error?: string;
  };
  candidates: Nav[];
  resolution: unknown;
};
export type Audit = {
  id: string;
  action: string;
  actor_name: string;
  created_at: string;
  object_id: string;
  details: unknown;
};
export type Member = {
  user_id: string;
  name: string;
  email: string;
  roles: string[];
  product_ids: string[];
  can_download: boolean;
};
export type Mailbox = {
  id: string;
  label: string;
  host: string;
  port: number;
  tls: "ssl" | "starttls";
  username: string;
  since: string;
  all_folders: boolean;
  send_id: boolean;
  enabled: boolean;
  credential_configured: boolean;
  last_sync: string | null;
  error: string | null;
};
export type MailItem = {
  id: string;
  document_id: string;
  category: string;
  title: string;
  sender: string;
  business_date: string | null;
  handling_mode: "task" | "receipt" | "pending" | "archive";
  priority: "high" | "normal" | "low";
  confidence: number;
  status: "pending" | "received" | "completed";
  revision: number;
  excerpt: string;
  created_at: string;
  attachment_count: number;
  products: { id: string; name: string }[];
  sources: { mailbox: string; username: string; folder: string }[];
  action: null | {
    id: string;
    suggested_action: string;
    due_at: string | null;
    status: "open" | "completed" | "cancelled";
    revision: number;
  };
};
export type MailDetail = {
  id: string;
  document_id: string;
  subject: string;
  sender: string;
  to: string;
  cc: string;
  sent_at: string;
  received_at: string;
  body: string;
  body_html: string | null;
  category: string;
  business_date: string | null;
  sources: { mailbox: string; username: string; folder: string }[];
  attachments: {
    id: string;
    filename: string;
    size: number;
    media_type: string;
    sha256: string;
  }[];
};

export const mailCategoryLabel = (s: string) =>
  ({
    nav_valuation: "净值 / 估值",
    futures_settlement: "期货结算",
    reconciliation_data: "对账 / 数据包",
    risk_monitoring: "风险 / 投监",
    open_day_calendar: "开放日 / 日历",
    contract_seal: "合同 / 用印",
    investor_redemption: "申赎 / 投资者",
    security: "安全提醒",
    action_required: "业务待办",
    completion_receipt: "完成通知",
    marketing: "营销信息",
    unknown: "待分类",
  })[s] || s;

export const sourceLabel = (s: string) =>
  ({
    manual: "人工录入",
    upload: "手动上传",
    email: "托管邮件",
    lifecycle_material: "生命周期材料",
    business_material: "业务材料",
    directory_import: "待整理目录导入",
  })[s] || s;
export const taskLabel = (s: string) =>
  ({
    parse: "解析待确认",
    conflict: "净值冲突",
    validation: "校验异常",
    missing: "材料未到",
    mailbox: "邮箱连接异常",
  })[s] || s;
export const stageLabel = (s: string) =>
  ({
    queued: "等待解析",
    processing: "处理中",
    review: "待人工确认",
    completed: "解析完成",
    manual_completed: "人工补录完成",
    open: "待处理",
    in_progress: "备案中",
    resolved: "已解决",
  })[s] || s;
export const lifecycleLabel = (s: string) =>
  ({
    active: "运作中",
    liquidating: "清算中",
    liquidated: "已清算",
    archived: "已归档",
  })[s] || s;
export { number } from "./format";
export const timestamp = (s: string | null | undefined) =>
  s
    ? new Date(s).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false })
    : "尚未同步";
export function previousFriday() {
  const d = new Date();
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(d);
  const part = (type: string) => parts.find((p) => p.type === type)!.value;
  const local = new Date(`${part("year")}-${part("month")}-${part("day")}T12:00:00Z`);
  const days = (local.getUTCDay() + 2) % 7 || 7;
  local.setUTCDate(local.getUTCDate() - days);
  return local.toISOString().slice(0, 10);
}

export function previousWeekday() {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const part = (type: string) => parts.find((p) => p.type === type)!.value;
  const local = new Date(`${part("year")}-${part("month")}-${part("day")}T12:00:00Z`);
  do {
    local.setUTCDate(local.getUTCDate() - 1);
  } while ([0, 6].includes(local.getUTCDay()));
  return local.toISOString().slice(0, 10);
}
