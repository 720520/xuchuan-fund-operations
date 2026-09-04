import { useState, type ReactNode } from "react";
import { Plus, ShieldCheck, Upload } from "lucide-react";
import { Button } from "./components/ui/button";
import { Input } from "./components/ui/input";
import {
  api,
  post,
  put,
  previousFriday,
  previousWeekday,
  lifecycleLabel,
  type Candidate,
  type Member,
  type Product,
  type Task,
} from "./api";

export function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
}) {
  return (
    <label className="form-field">
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  );
}
export function ActionForm({
  children,
  submit,
  done,
  label = "保存",
  disabled = false,
}: {
  children: ReactNode;
  submit: (data: FormData) => Promise<unknown>;
  done: () => void;
  label?: string;
  disabled?: boolean;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  return (
    <form
      className="live-form"
      onSubmit={async (e) => {
        e.preventDefault();
        if (busy) return;
        const data = new FormData(e.currentTarget);
        setBusy(true);
        setError("");
        try {
          await submit(data);
          done();
        } catch (e) {
          setError((e as Error).message);
        } finally {
          setBusy(false);
        }
      }}
    >
      <fieldset disabled={busy}>{children}</fieldset>
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
      <div className="form-actions">
        <span>
          <ShieldCheck size={13} />
          操作将记录账号与时间
        </span>
        <Button type="submit" disabled={busy || disabled}>
          {busy ? "正在提交…" : label}
        </Button>
      </div>
    </form>
  );
}
export const val = (f: FormData, name: string) => String(f.get(name) || "").trim();

export function ProductForm({
  managerId,
  candidate,
  documentId,
  filing = false,
  done,
}: {
  managerId: string;
  candidate?: Candidate;
  documentId?: string;
  filing?: boolean;
  done: () => void;
}) {
  return (
    <ActionForm
      done={done}
      label={candidate ? "确认并加入产品" : filing ? "发起备案" : "创建产品"}
      submit={async (f) => {
        const payload = {
          code: val(f, "code"),
          name: val(f, "name"),
          currency: val(f, "currency"),
          strategy: val(f, "strategy"),
          shares: val(f, "shares")
            .split(/[，,]/)
            .map((s) => s.trim()),
        };
        await post(
          documentId
            ? `/documents/${documentId}/confirm-product`
            : `/managers/${managerId}/${filing ? "product-filings" : "products"}`,
          payload,
        );
      }}
    >
      {candidate && (
        <p className="inline-note">
          以下信息来自附件，尚未写入台账。请核实产品归属和份额，确认后重新解析原件。
        </p>
      )}
      {filing && (
        <p className="inline-note">
          第一阶段仅记录备案事项和拟设产品信息；完整备案节点暂不启用。备案结束后可一键加入产品台账。
        </p>
      )}
      <Field label="产品全称">
        <Input name="name" defaultValue={candidate?.product_name} required maxLength={200} />
      </Field>
      <div className="field-pair">
        <Field label="产品／备案代码">
          <Input name="code" defaultValue={candidate?.product_code} required maxLength={80} />
        </Field>
        <Field label="币种">
          <select name="currency" defaultValue="CNY">
            <option>CNY</option>
            <option>USD</option>
            <option>HKD</option>
          </select>
        </Field>
      </div>
      <Field label="份额类别" hint="多个类别用逗号分隔；名称需与托管材料一致">
        <Input
          name="shares"
          defaultValue={candidate?.share_class || "A"}
          required
          maxLength={500}
        />
      </Field>
      <Field label="投资策略（选填）">
        <Input name="strategy" maxLength={80} />
      </Field>
      {!filing && (
        <p className="inline-note">默认纳入日频应收台账，11:00 截止；管理员可修改频率与应收范围。</p>
      )}
    </ActionForm>
  );
}

function NavFields({
  products,
  index = 0,
  task,
}: {
  products: Product[];
  index?: number;
  task?: Task;
}) {
  const [selected, setSelected] = useState(task?.product_id || products[0]?.id || "");
  const product = products.find((p) => p.id === selected),
    prefix = `nav${index}-`;
  return (
    <div className="nav-entry">
      <div className="field-pair">
        <Field label="产品">
          <select
            name={prefix + "product_id"}
            required
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
          >
            {products.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="份额类别">
          <select
            name={prefix + "share_id"}
            required
            key={selected}
            defaultValue={task?.share_id || product?.shares[0]?.id}
          >
            {product?.shares.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <div className="field-pair">
        <Field
          label="估值日期"
          hint={product?.frequency === "weekly" ? "默认上周五，可按托管材料修改" : undefined}
        >
          <Input
            type="date"
            name={prefix + "valuation_date"}
            required
            key={selected + "-date"}
            defaultValue={
              task?.valuation_date ||
              (product?.frequency === "weekly" ? previousFriday() : previousWeekday())
            }
          />
        </Field>
        <Field label="单位净值">
          <Input
            inputMode="decimal"
            name={prefix + "unit_nav"}
            required
            placeholder="请按原件填写"
          />
        </Field>
      </div>
      <div className="field-pair">
        <Field label="累计净值（选填）">
          <Input inputMode="decimal" name={prefix + "accumulated_nav"} />
        </Field>
        <Field label="资产净值（元，选填）">
          <Input inputMode="decimal" name={prefix + "net_assets"} />
        </Field>
      </div>
      <Field label="总份额（选填）">
        <Input inputMode="decimal" name={prefix + "total_shares"} />
      </Field>
    </div>
  );
}

export function NavForm({
  managerId,
  products,
  task,
  done,
}: {
  managerId: string;
  products: Product[];
  task?: Task;
  done: () => void;
}) {
  const [count, setCount] = useState(1);
  return (
    <ActionForm
      done={done}
      disabled={!products.length}
      label={task ? "补录并完成材料核对" : "保存并校验"}
      submit={(f) => {
        const records = Array.from({ length: count }, (_, i) =>
          Object.fromEntries(
            [
              "product_id",
              "share_id",
              "valuation_date",
              "unit_nav",
              "accumulated_nav",
              "net_assets",
              "total_shares",
            ].map((k) => [k, val(f, `nav${i}-${k}`) || null]),
          ),
        );
        return task
          ? post(`/tasks/${task.id}/complete-material`, {
              revision: task.revision,
              reason: val(f, "reason"),
              complete_material: f.get("complete") === "on",
              records,
            })
          : post(`/managers/${managerId}/nav`, records[0]);
      }}
    >
      <p className="inline-note">
        来源显示当前运营账号，无需二次复核。旧记录不修改；出现同日冲突时请到异常中心选定有效版本。
      </p>
      {Array.from({ length: count }, (_, i) => (
        <NavFields key={i} index={i} products={products} task={task} />
      ))}
      {task && (
        <>
          <Button
            type="button"
            variant="outline"
            onClick={() => setCount((c) => c + 1)}
            disabled={count >= 100}
          >
            <Plus />
            增加一条净值
          </Button>
          <Field label="核对结论">
            <textarea name="reason" required maxLength={2000} rows={3} />
          </Field>
          <label className="check-line">
            <input type="checkbox" name="complete" required />
            我已核对原始材料，并补齐该材料涉及的所有净值记录。
          </label>
        </>
      )}
    </ActionForm>
  );
}

export function UploadForm({
  managerId,
  products,
  done,
}: {
  managerId: string;
  products: Product[];
  done: () => void;
}) {
  const [name, setName] = useState("");
  return (
    <ActionForm
      done={done}
      label="归档并提交解析"
      submit={(f) => api(`/managers/${managerId}/documents`, { method: "POST", body: f })}
    >
      <Field label="关联产品">
        <select name="product_id" defaultValue="">
          <option value="">由附件识别产品（新产品进入待确认）</option>
          {products.map((p) => (
            <option value={p.id} key={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </Field>
      <label className="live-dropzone">
        <Upload size={27} />
        <strong>{name || "选择需要归档的附件"}</strong>
        <span>单份文件上限 25 MiB · 原件永久保留</span>
        <input
          type="file"
          name="file"
          required
          onChange={(e) => setName(e.target.files?.[0]?.name || "")}
        />
      </label>
      <p className="inline-note">
        已支持明确表头的 XLSX、XLS、CSV；未知托管格式和 PDF
        将归档并进入待确认，不会猜测净值。文件归档后由后台任务解析。
      </p>
    </ActionForm>
  );
}

export function ScheduleForm({ product, done }: { product: Product; done: () => void }) {
  return (
    <ActionForm
      done={done}
      submit={(f) =>
        put(`/products/${product.id}/schedule`, {
          expected: f.get("expected") === "on",
          frequency: val(f, "frequency"),
          weekday: Number(val(f, "weekday")),
          cutoff: val(f, "cutoff"),
        })
      }
    >
      <p className="inline-note">{product.name} · 配置由本牌照管理员维护。</p>
      <label className="check-line">
        <input name="expected" type="checkbox" defaultChecked={product.expected} />
        纳入应收检查
      </label>
      <div className="field-pair">
        <Field label="发送频率">
          <select name="frequency" defaultValue={product.frequency}>
            <option value="daily">日频</option>
            <option value="weekly">周频</option>
            <option value="off">不发送</option>
          </select>
        </Field>
        <Field label="每日接收截止时间">
          <Input name="cutoff" type="time" required defaultValue={product.cutoff} />
        </Field>
      </div>
      <Field label="周频对应估值日">
        <select name="weekday" defaultValue={product.weekday}>
          {["周一", "周二", "周三", "周四", "周五", "周六", "周日"].map((d, i) => (
            <option key={i} value={i}>
              {d}
            </option>
          ))}
        </select>
      </Field>
      <p className="inline-note">交易日历尚未联调，应收检查须选择估值日期；法定假日不自动推算。</p>
    </ActionForm>
  );
}

export function LifecycleForm({ product, done }: { product: Product; done: () => void }) {
  const [status, setStatus] = useState<Product["lifecycle_status"]>(
    product.lifecycle_status === "active"
      ? "liquidating"
      : product.lifecycle_status === "liquidating"
        ? "liquidated"
        : "active",
  );
  return (
    <ActionForm
      done={done}
      label="确认变更产品状态"
      submit={(form) => {
        const file = form.get("material");
        if (file instanceof File && file.size === 0) form.delete("material");
        return api(`/products/${product.id}/lifecycle`, { method: "POST", body: form });
      }}
    >
      <p className="inline-note">
        {product.name} · 当前状态：{lifecycleLabel(product.lifecycle_status)}。状态变化将记录实际操作账号。
      </p>
      <Field label="变更为">
        <select
          name="status"
          value={status}
          onChange={(event) => setStatus(event.target.value as Product["lifecycle_status"])}
        >
          <option value="active">运作中</option>
          <option value="liquidating">清算中</option>
          <option value="liquidated">已清算</option>
          <option value="archived">已归档</option>
        </select>
      </Field>
      <Field label={status === "liquidated" ? "清算完成日期" : "状态生效日期"}>
        <Input name="effective_date" type="date" required={status === "liquidated"} />
      </Field>
      <Field label="变更原因">
        <textarea name="reason" required rows={4} maxLength={2000} />
      </Field>
      <Field
        label="清算或状态依据材料"
        hint={status === "liquidated" ? "已清算必须上传清算报告或托管确认材料" : "其他状态可选"}
      >
        <Input name="material" type="file" required={status === "liquidated"} />
      </Field>
      {status === "active" ? (
        <p className="inline-note">恢复运作后不会自动恢复应收规则，请再到“应收设置”确认发送频率。</p>
      ) : status === "liquidated" || status === "archived" ? (
        <p className="inline-note">
          保存后将停止净值应收并从日常列表隐藏；历史净值、邮件、材料和处理记录均保留。
        </p>
      ) : (
        <p className="inline-note">清算中产品仍显示在日常列表，应收规则可由管理员单独调整。</p>
      )}
    </ActionForm>
  );
}

export const roles: Record<string, string> = {
  admin: "系统管理员",
  operator: "运营人员",
  operations_lead: "运营负责人",
  manager_head: "管理层（本牌照）",
  group_viewer: "集团查看授权",
  fund_manager: "基金经理",
  trader: "交易员",
  compliance: "合规风控",
  finance: "财务",
};
export function MemberForm({
  managerId,
  member,
  products,
  done,
}: {
  managerId: string;
  member?: Member;
  products: Product[];
  done: () => void;
}) {
  return (
    <ActionForm
      done={done}
      label={member ? "更新授权" : "创建账号"}
      submit={(f) => {
        const access = {
          roles: f.getAll("roles"),
          can_download: f.get("download") === "on",
          product_ids: f.getAll("products"),
        };
        return member
          ? put(`/managers/${managerId}/members/${member.user_id}`, access)
          : post(`/managers/${managerId}/members`, {
              ...access,
              name: val(f, "name"),
              email: val(f, "email"),
              password: String(f.get("password")),
            });
      }}
    >
      {member ? (
        <p>
          {member.name} · {member.email}
        </p>
      ) : (
        <>
          <Field label="姓名">
            <Input name="name" required maxLength={80} />
          </Field>
          <Field label="登录邮箱">
            <Input name="email" type="email" required autoComplete="off" />
          </Field>
          <Field label="初始密码（12–128 位）">
            <Input
              name="password"
              type="password"
              minLength={12}
              maxLength={128}
              required
              autoComplete="new-password"
            />
          </Field>
        </>
      )}
      <div className="role-grid">
        {Object.entries(roles).map(([key, label]) => (
          <label key={key} className="check-line">
            <input
              name="roles"
              value={key}
              type="checkbox"
              defaultChecked={member?.roles.includes(key)}
            />
            {label}
          </label>
        ))}
      </div>
      <label className="check-line">
        <input name="download" type="checkbox" defaultChecked={member?.can_download} />
        允许下载本牌照原始资料（独立授权）
      </label>
      <Field label="基金经理／交易员／财务可查看的产品">
        <div className="grant-list">
          {products.length ? (
            products.map((p) => (
              <label key={p.id} className="check-line">
                <input
                  name="products"
                  type="checkbox"
                  value={p.id}
                  defaultChecked={member?.product_ids.includes(p.id)}
                />
                {p.name}
              </label>
            ))
          ) : (
            <small>暂无产品</small>
          )}
        </div>
      </Field>
      <p className="inline-note">
        管理员拥有当前牌照全部页面和操作权限。同集团运营可查看其他牌照，但只能操作自己所属牌照；异常由牌照内全员共享处理。
      </p>
    </ActionForm>
  );
}
