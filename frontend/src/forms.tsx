import { useState, type ReactNode } from "react";
import { Plus, ShieldCheck, Upload } from "lucide-react";
import { Button } from "./components/ui/button";
import { Input } from "./components/ui/input";
import {
  api,
  downloadFile,
  post,
  put,
  previousFriday,
  lifecycleLabel,
  type Candidate,
  type Doc,
  type Investor,
  type InvestorBankAccount,
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
        <p className="inline-note">默认纳入日频应收台账，15:00 截止；管理员可修改频率与应收范围。</p>
      )}
    </ActionForm>
  );
}

function NavFields({
  products,
  index = 0,
  task,
  suggestedDate,
}: {
  products: Product[];
  index?: number;
  task?: Task;
  suggestedDate?: string;
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
              (product?.frequency === "weekly" ? previousFriday() : suggestedDate || "")
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
  suggestedDate,
  done,
}: {
  managerId: string;
  products: Product[];
  task?: Task;
  suggestedDate?: string;
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
        <NavFields key={i} index={i} products={products} task={task} suggestedDate={suggestedDate} />
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

export function NavExportForm({
  managerId,
  products,
  initialProductId,
  suggestedDate,
  done,
}: {
  managerId: string;
  products: Product[];
  initialProductId?: string;
  suggestedDate?: string;
  done: () => void;
}) {
  const defaultDate = suggestedDate || previousFriday();
  const [selectedProductIds, setSelectedProductIds] = useState<Set<string>>(
    () =>
      new Set(
        initialProductId && products.some((product) => product.id === initialProductId)
          ? [initialProductId]
          : products.map((product) => product.id),
      ),
  );
  return (
    <ActionForm
      done={done}
      disabled={!products.length || !selectedProductIds.size}
      label="下载 Excel"
      submit={(form) => {
        const startDate = val(form, "start_date");
        const endDate = val(form, "end_date");
        const params = new URLSearchParams({
          start_date: startDate,
          end_date: endDate,
        });
        products.forEach((product) => {
          if (selectedProductIds.has(product.id)) params.append("product_id", product.id);
        });
        return downloadFile(
          `/managers/${managerId}/nav/export?${params.toString()}`,
          `产品净值_${startDate.replaceAll("-", "")}_${endDate.replaceAll("-", "")}.xlsx`,
        );
      }}
    >
      <p className="inline-note">
        导出选定估值日范围内的当前有效版本，并保留来源记录和原件编号便于追溯。
      </p>
      <div className="field-pair">
        <Field label="开始估值日">
          <Input name="start_date" type="date" required defaultValue={defaultDate} />
        </Field>
        <Field label="结束估值日">
          <Input name="end_date" type="date" required defaultValue={defaultDate} />
        </Field>
      </div>
      <Field
        label={`产品范围（已选 ${selectedProductIds.size} / ${products.length} 个）`}
        hint="所选产品的净值会按估值日汇总在同一个工作表中"
      >
        <div className="nav-export-selection-head">
          <span>只显示当前账号有权查看的产品</span>
          <div className="row-actions">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setSelectedProductIds(new Set(products.map((product) => product.id)))}
            >
              全选
            </Button>
            <Button type="button" variant="ghost" onClick={() => setSelectedProductIds(new Set())}>
              清空
            </Button>
          </div>
        </div>
        <div className="material-product-list nav-export-product-list">
          {products.map((product) => (
            <label key={product.id} title={`${product.code} · ${product.name}`}>
              <input
                type="checkbox"
                checked={selectedProductIds.has(product.id)}
                onChange={(event) => {
                  const next = new Set(selectedProductIds);
                  if (event.target.checked) next.add(product.id);
                  else next.delete(product.id);
                  setSelectedProductIds(next);
                }}
              />
              <span>{product.code} · {product.name}</span>
            </label>
          ))}
        </div>
      </Field>
    </ActionForm>
  );
}

export function UploadForm({
  managerId,
  products,
  investors,
  initialProductId,
  initialInvestorId,
  done,
}: {
  managerId: string;
  products: Product[];
  investors: Investor[];
  initialProductId?: string;
  initialInvestorId?: string;
  done: () => void;
}) {
  const [name, setName] = useState("");
  const fixedProduct = initialProductId
    ? products.find((product) => product.id === initialProductId)
    : undefined;
  const fixedInvestor = initialInvestorId
    ? investors.find((investor) => investor.id === initialInvestorId)
    : undefined;
  return (
    <ActionForm
      done={done}
      label="归档资料"
      submit={(f) => api(`/managers/${managerId}/documents`, { method: "POST", body: f })}
    >
      {fixedProduct ? (
        <div className="upload-bound-scope">
          <span>归档到产品</span>
          <strong>{fixedProduct.name}</strong>
          <small>{fixedProduct.code} · 保存时自动建立产品资料关系</small>
          <input type="hidden" name="product_id" value={fixedProduct.id} />
          <input type="hidden" name="material_scope" value="product" />
        </div>
      ) : !fixedInvestor ? (
        <Field label="初始关联产品">
          <select name="product_id" defaultValue="">
            <option value="">暂不关联，由后续整理确认</option>
            {products.map((p) => (
              <option value={p.id} key={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          <small>归档后可在资料中心调整为一个或多个产品。</small>
        </Field>
      ) : null}
      {fixedInvestor ? (
        <div className="upload-bound-scope investor">
          <span>归档到投资者</span>
          <strong>{fixedInvestor.display_name}</strong>
          <small>保存时自动按投资者敏感资料归档，资料类别可随后确认</small>
          <input type="hidden" name="investor_id" value={fixedInvestor.id} />
          <input type="hidden" name="material_scope" value="investor" />
        </div>
      ) : !fixedProduct && investors.length > 0 ? (
        <Field label="投资者敏感资料">
          <select name="investor_id" defaultValue="">
            <option value="">不是投资者资料，或稍后再关联</option>
            {investors.map((investor) => (
              <option value={investor.id} key={investor.id}>
                {investor.display_name}
              </option>
            ))}
          </select>
          <small>选择后将立即按投资者敏感资料归档，并等待人工确认类别。</small>
        </Field>
      ) : null}
      <label className="live-dropzone">
        <Upload size={27} />
        <strong>{name || "选择需要归档的资料"}</strong>
        <span>单份文件上限 25 MiB · 原件只读归档</span>
        <input
          type="file"
          name="file"
          required
          onChange={(e) => setName(e.target.files?.[0]?.name || "")}
        />
      </label>
      <p className="inline-note">
        {fixedProduct || fixedInvestor
          ? "系统保存原件并直接归入当前目录，不进入净值解析。上传后可补充资料类别、业务日期以及另一侧关联。"
          : "系统先保存原件。可识别的净值材料继续进入解析；合同、报告及其他文件保留为资料，等待后续整理，不会猜测业务内容。"}
      </p>
    </ActionForm>
  );
}

export function MaterialForm({
  document,
  products,
  investors,
  done,
}: {
  document: Doc;
  products: Product[];
  investors: Investor[];
  done: () => void;
}) {
  const linked = new Set(
    document.product_ids ||
      document.products?.map((product) => product.id) ||
      (document.product_id ? [document.product_id] : []),
  );
  const linkedInvestors = new Set(document.investor_ids || []);
  const inferredCategory =
    document.category ||
    document.metadata_json.material_category ||
    (document.source === "lifecycle_material"
      ? "operation_evidence"
      : document.job?.status === "completed" &&
          (document.job.result.record_count || document.job.result.record_ids?.length)
        ? "nav_valuation"
        : "");
  const [category, setCategory] = useState(inferredCategory);
  const [sensitivity, setSensitivity] = useState<"standard" | "investor_sensitive">(
    document.sensitivity || (linkedInvestors.size ? "investor_sensitive" : "standard"),
  );
  return (
    <ActionForm
      done={done}
      label="确认整理结果"
      submit={(form) =>
        put(`/documents/${document.id}/material`, {
          revision: document.material_revision || 0,
          category: val(form, "category"),
          material_type: val(form, "material_type") || null,
          title: val(form, "title") || null,
          business_date: val(form, "business_date") || null,
          period_start: val(form, "period_start") || null,
          period_end: val(form, "period_end") || null,
          product_ids: form.getAll("product_ids").map(String),
          investor_ids: form.getAll("investor_ids").map(String),
          sensitivity: val(form, "sensitivity"),
          notes: val(form, "notes"),
          confirmed: form.get("confirmed") === "on",
        })
      }
    >
      <p className="inline-note">
        整理结果与原件分开保存。修改分类和产品关系不会改动文件、接收时间或邮件状态。
      </p>
      <Field label="资料标题" hint="用于资料中心展示，不修改原文件名">
        <Input
          name="title"
          maxLength={500}
          defaultValue={document.title || document.metadata_json.subject || ""}
          placeholder={document.filename}
        />
      </Field>
      <Field label="资料类别">
        <select
          name="category"
          required
          value={category}
          onChange={(event) => {
            setCategory(event.target.value);
            if (["investor_qualification", "subscription_redemption"].includes(event.target.value)) {
              setSensitivity("investor_sensitive");
            }
          }}
        >
          <option value="" disabled>请选择资料类别</option>
          <option value="nav_valuation">净值与估值</option>
          <option value="contract">合同与协议</option>
          <option value="investor_qualification">投资者准入与适当性</option>
          <option value="subscription_redemption">认申购与赎回材料</option>
          <option value="filing">产品备案与变更</option>
          <option value="custody_account">托管及账户材料</option>
          <option value="periodic_report">定期报告</option>
          <option value="risk_compliance">风险与合规通知</option>
          <option value="operation_evidence">运营处理凭证</option>
          <option value="other">其他资料</option>
        </select>
      </Field>
      <Field label="资料具体类型" hint="用于适当性清单和后续自动归档；不确定时可留空">
        <select name="material_type" defaultValue={document.material_type || ""}>
          <option value="">暂不细分</option>
          <optgroup label="投资者通用资料">
            <option value="qualified_investor_commitment">合格投资者承诺函</option>
            <option value="risk_questionnaire">风险测评问卷</option>
            <option value="investor_information_form">投资者信息表</option>
            <option value="identity_front">身份证正面</option>
            <option value="identity_back">身份证反面</option>
            <option value="identity_document">其他身份证明</option>
            <option value="asset_proof">资产规模／收入证明</option>
            <option value="tax_declaration">税收身份声明</option>
            <option value="professional_investor_proof">专业投资者证明</option>
            <option value="institution_certificate">机构证明材料</option>
            <option value="representative_identity">法人／经办人证明</option>
            <option value="authorization">授权文件</option>
            <option value="product_filing_certificate">产品备案证明</option>
            <option value="bank_account_proof">银行账户证明</option>
            <option value="special_object_confirmation">特定对象确认材料</option>
          </optgroup>
          <optgroup label="产品业务资料">
            <option value="contract">合同</option>
            <option value="risk_disclosure">风险揭示书</option>
            <option value="supplemental_agreement">补充协议</option>
            <option value="subscription_form">认申购申请</option>
            <option value="redemption_form">赎回申请</option>
            <option value="double_recording">双录资料</option>
            <option value="cooling_off_callback">冷静期回访</option>
            <option value="transfer_voucher">划款凭证</option>
            <option value="custom">其他细类</option>
          </optgroup>
        </select>
      </Field>
      <Field label="关联投资者" hint="可多选；姓名相同但身份未核实时不要直接合并">
        <div className="material-product-list">
          {investors.length ? investors.map((investor) => (
            <label key={investor.id}>
              <input
                type="checkbox"
                name="investor_ids"
                value={investor.id}
                defaultChecked={linkedInvestors.has(investor.id)}
                onChange={(event) => {
                  if (event.target.checked) setSensitivity("investor_sensitive");
                }}
              />
              <span>{investor.display_name}</span>
            </label>
          )) : <small>尚未建立投资者，可先到投资者资料页面登记</small>}
        </div>
      </Field>
      <Field label="敏感级别">
        <select name="sensitivity" value={sensitivity} onChange={(event) => setSensitivity(event.target.value as "standard" | "investor_sensitive")}>
          <option value="standard">普通业务资料</option>
          <option value="investor_sensitive">投资者敏感资料</option>
        </select>
      </Field>
      <Field label="关联产品" hint="可多选；不确定时可以暂不关联">
        <div className="material-product-list">
          {products.length ? products.map((product) => (
            <label key={product.id}>
              <input
                type="checkbox"
                name="product_ids"
                value={product.id}
                defaultChecked={linked.has(product.id)}
              />
              <span>{product.name}</span>
            </label>
          )) : <small>当前没有可关联产品</small>}
        </div>
      </Field>
      <div className="field-pair">
        <Field label="业务日期（选填）">
          <Input name="business_date" type="date" defaultValue={document.business_date || ""} />
        </Field>
        <Field label="资料期间开始（选填）">
          <Input name="period_start" type="date" defaultValue={document.period_start || ""} />
        </Field>
      </div>
      <Field label="资料期间结束（选填）">
        <Input name="period_end" type="date" defaultValue={document.period_end || ""} />
      </Field>
      <Field label="整理说明（选填）">
        <textarea name="notes" maxLength={2000} rows={3} defaultValue={document.notes || ""} />
      </Field>
      <p className="inline-note">
        “净值与估值”会进入净值解析；其他类别只保存整理结果和原件关系。
      </p>
      <label className="check-line">
        <input type="checkbox" name="confirmed" required />
        我已核对资料类别、日期和产品关系。
      </label>
    </ActionForm>
  );
}

export function InvestorForm({
  managerId,
  investor,
  products,
  documents,
  done,
}: {
  managerId: string;
  investor?: Investor;
  products: Product[];
  documents: Doc[];
  done: () => void;
}) {
  const linked = new Set(investor?.product_ids || []);
  const [investorType, setInvestorType] = useState<Investor["investor_type"]>(investor?.investor_type || "individual");
  const [suitabilityClass, setSuitabilityClass] = useState<NonNullable<Investor["suitability_class"]>>(investor?.suitability_class || "unknown");
  const sourceDocuments = documents.filter((document) =>
    document.sensitivity === "investor_sensitive" &&
    (!investor || document.investor_ids?.includes(investor.id)),
  );
  const nullable = (form: FormData, name: string) => val(form, name) || null;
  return (
    <ActionForm
      done={done}
      label={investor ? "保存投资者信息" : "建立投资者"}
      submit={(form) => {
        const payload = {
          revision: investor?.revision || 0,
          investor_type: val(form, "investor_type"),
          display_name: val(form, "display_name"),
          suitability_class: val(form, "suitability_class"),
          professional_investor_type: nullable(form, "professional_investor_type"),
          certificate_type: nullable(form, "certificate_type"),
          certificate_number: nullable(form, "certificate_number"),
          clear_certificate_number: form.get("clear_certificate_number") === "on",
          certificate_valid_until: nullable(form, "certificate_valid_until"),
          nationality_or_region: nullable(form, "nationality_or_region"),
          contact_email: nullable(form, "contact_email"),
          contact_phone: nullable(form, "contact_phone"),
          specific_object_status: val(form, "specific_object_status"),
          specific_object_confirmed_at: nullable(form, "specific_object_confirmed_at"),
          risk_level: nullable(form, "risk_level"),
          risk_assessed_at: nullable(form, "risk_assessed_at"),
          risk_expires_at: nullable(form, "risk_expires_at"),
          qualified_material_status: val(form, "qualified_material_status"),
          qualified_material_from: nullable(form, "qualified_material_from"),
          qualified_material_until: nullable(form, "qualified_material_until"),
          profile_source_document_id: nullable(form, "profile_source_document_id"),
          suitability_source_document_id: nullable(form, "suitability_source_document_id"),
          status: val(form, "status"),
          source: val(form, "source"),
          product_ids: form.getAll("product_ids").map(String),
          notes: val(form, "notes"),
        };
        return investor
          ? put(`/investors/${investor.id}`, payload)
          : post(`/managers/${managerId}/investors`, payload);
      }}
    >
      <p className="inline-note">字段保存当前有效信息，来源原件保留在资料中心。相同姓名不会自动合并。</p>
      <h3 className="form-section-title">主体基本信息</h3>
      <Field label="投资者名称">
        <Input name="display_name" required maxLength={200} defaultValue={investor?.display_name || ""} />
      </Field>
      <div className="field-pair">
        <Field label="投资者类型">
          <select name="investor_type" value={investorType} onChange={(event) => setInvestorType(event.target.value as Investor["investor_type"])}>
            <option value="individual">个人投资者</option>
            <option value="institution">机构投资者</option>
            <option value="fund_product">私募基金产品</option>
            <option value="asset_management">资管计划</option>
            <option value="manager_co_investment">管理人跟投</option>
            <option value="other">其他</option>
          </select>
        </Field>
        <Field label="核对状态">
          <select name="status" defaultValue={investor?.status || "pending"}>
            <option value="pending">待核对</option>
            <option value="confirmed">已核对</option>
            <option value="historical">历史投资者</option>
          </select>
        </Field>
      </div>
      <div className="field-pair">
        <Field label="证件类型">
          <Input name="certificate_type" maxLength={50} defaultValue={investor?.certificate_type || ""} placeholder={investorType === "individual" ? "身份证" : "统一社会信用代码"} />
        </Field>
        <Field label="证件号码" hint={investor?.certificate_number_masked ? `当前：${investor.certificate_number_masked}；留空保持不变` : "保存后只显示掩码"}>
          <Input name="certificate_number" minLength={4} maxLength={100} autoComplete="off" />
        </Field>
      </div>
      {investor?.certificate_number_masked && (
        <label className="check-line"><input type="checkbox" name="clear_certificate_number" />清除已保存的证件号码</label>
      )}
      <div className="field-pair">
        <Field label="证件有效期"><Input name="certificate_valid_until" type="date" defaultValue={investor?.certificate_valid_until || ""} /></Field>
        <Field label="国籍／注册地"><Input name="nationality_or_region" maxLength={100} defaultValue={investor?.nationality_or_region || ""} /></Field>
      </div>
      <div className="field-pair">
        <Field label="联系邮箱"><Input name="contact_email" type="email" maxLength={254} defaultValue={investor?.contact_email || ""} /></Field>
        <Field label="联系电话"><Input name="contact_phone" maxLength={50} defaultValue={investor?.contact_phone || ""} /></Field>
      </div>
      <h3 className="form-section-title">适当性信息</h3>
      <div className="field-pair">
        <Field label="适当性分类">
          <select name="suitability_class" value={suitabilityClass} onChange={(event) => setSuitabilityClass(event.target.value as NonNullable<Investor["suitability_class"]>)}>
            <option value="unknown">待确认</option>
            <option value="ordinary">普通投资者</option>
            <option value="professional">专业投资者</option>
          </select>
        </Field>
        <Field label="专业投资者类型">
          <Input name="professional_investor_type" maxLength={100} disabled={suitabilityClass !== "professional"} defaultValue={investor?.professional_investor_type || ""} placeholder="仅专业投资者填写" />
        </Field>
      </div>
      <div className="field-pair">
        <Field label="风险等级"><Input name="risk_level" maxLength={30} defaultValue={investor?.risk_level || ""} placeholder="如 C4" /></Field>
        <Field label="特定对象确认状态">
          <select name="specific_object_status" defaultValue={investor?.specific_object_status || "unknown"}>
            <option value="unknown">待确认</option><option value="pending">处理中</option><option value="confirmed">已确认</option><option value="expired">已失效</option><option value="not_applicable">不适用</option>
          </select>
        </Field>
      </div>
      <div className="field-pair">
        <Field label="风险测评日期"><Input name="risk_assessed_at" type="date" defaultValue={investor?.risk_assessed_at || ""} /></Field>
        <Field label="风险测评到期日"><Input name="risk_expires_at" type="date" defaultValue={investor?.risk_expires_at || ""} /></Field>
      </div>
      <div className="field-pair">
        <Field label="特定对象确认日期"><Input name="specific_object_confirmed_at" type="date" defaultValue={investor?.specific_object_confirmed_at || ""} /></Field>
        <Field label="合格材料状态">
          <select name="qualified_material_status" defaultValue={investor?.qualified_material_status || "unknown"}>
            <option value="unknown">待确认</option><option value="missing">缺失</option><option value="valid">有效</option><option value="expired">已到期</option><option value="not_applicable">不适用</option>
          </select>
        </Field>
      </div>
      <div className="field-pair">
        <Field label="合格材料建立日期"><Input name="qualified_material_from" type="date" defaultValue={investor?.qualified_material_from || ""} /></Field>
        <Field label="合格材料到期日"><Input name="qualified_material_until" type="date" defaultValue={investor?.qualified_material_until || ""} /></Field>
      </div>
      <h3 className="form-section-title">字段来源</h3>
      <div className="field-pair">
        <Field label="基础信息来源原件">
          <select name="profile_source_document_id" defaultValue={investor?.profile_source_document_id || ""}><option value="">暂未关联</option>{sourceDocuments.map((document) => <option key={document.id} value={document.id}>{document.title || document.filename}</option>)}</select>
        </Field>
        <Field label="适当性信息来源原件">
          <select name="suitability_source_document_id" defaultValue={investor?.suitability_source_document_id || ""}><option value="">暂未关联</option>{sourceDocuments.map((document) => <option key={document.id} value={document.id}>{document.title || document.filename}</option>)}</select>
        </Field>
      </div>
      <Field label="信息来源">
        <select name="source" defaultValue={investor?.source || "manual"}>
          <option value="manual">人工登记</option>
          <option value="directory_reference">待整理目录索引</option>
          <option value="material">已归档材料</option>
        </select>
      </Field>
      <Field label="关联产品" hint="一个投资者可关联多个产品">
        <div className="material-product-list">
          {products.length ? products.map((product) => (
            <label key={product.id}>
              <input type="checkbox" name="product_ids" value={product.id} defaultChecked={linked.has(product.id)} />
              <span>{product.name}</span>
            </label>
          )) : <small>当前没有可关联产品</small>}
        </div>
      </Field>
      <Field label="核对说明（选填）">
        <textarea name="notes" maxLength={2000} rows={4} defaultValue={investor?.notes || ""} />
      </Field>
    </ActionForm>
  );
}

export function InvestorBankAccountForm({
  investor,
  account,
  products,
  documents,
  done,
}: {
  investor: Investor;
  account?: InvestorBankAccount;
  products: Product[];
  documents: Doc[];
  done: () => void;
}) {
  const linked = new Set(account?.product_ids || []);
  const sourceDocuments = documents.filter((document) =>
    document.sensitivity === "investor_sensitive" && document.investor_ids?.includes(investor.id),
  );
  return (
    <ActionForm
      done={done}
      label={account ? "保存银行账户" : "新增银行账户"}
      submit={(form) => {
        const payload = {
          revision: account?.revision || 0,
          account_name: val(form, "account_name"),
          account_number: val(form, "account_number") || null,
          bank_name: val(form, "bank_name"),
          branch_name: val(form, "branch_name"),
          currency: val(form, "currency") || "CNY",
          status: val(form, "status"),
          source_document_id: val(form, "source_document_id") || null,
          product_ids: form.getAll("product_ids").map(String),
        };
        return account
          ? put(`/investor-bank-accounts/${account.id}`, payload)
          : post(`/investors/${investor.id}/bank-accounts`, payload);
      }}
    >
      <p className="inline-note">账号加密保存，页面和接口只返回掩码。停用账户后仍保留历史记录。</p>
      <div className="field-pair">
        <Field label="户名"><Input name="account_name" required maxLength={200} defaultValue={account?.account_name || investor.display_name} /></Field>
        <Field label="账号" hint={account ? `当前：${account.account_number_masked}；留空保持不变` : "保存后只显示掩码"}>
          <Input name="account_number" required={!account} minLength={4} maxLength={100} autoComplete="off" />
        </Field>
      </div>
      <div className="field-pair">
        <Field label="银行"><Input name="bank_name" required maxLength={200} defaultValue={account?.bank_name || ""} /></Field>
        <Field label="开户行"><Input name="branch_name" maxLength={300} defaultValue={account?.branch_name || ""} /></Field>
      </div>
      <div className="field-pair">
        <Field label="币种"><Input name="currency" required minLength={3} maxLength={10} defaultValue={account?.currency || "CNY"} /></Field>
        <Field label="状态"><select name="status" defaultValue={account?.status || "active"}><option value="active">有效</option><option value="inactive">停用</option></select></Field>
      </div>
      <Field label="账户证明原件">
        <select name="source_document_id" defaultValue={account?.source_document_id || ""}><option value="">暂未关联</option>{sourceDocuments.map((document) => <option key={document.id} value={document.id}>{document.title || document.filename}</option>)}</select>
      </Field>
      <Field label="适用产品" hint="不选择表示该账户暂未限定产品">
        <div className="material-product-list">{products.map((product) => <label key={product.id}><input type="checkbox" name="product_ids" value={product.id} defaultChecked={linked.has(product.id)} /><span>{product.name}</span></label>)}</div>
      </Field>
    </ActionForm>
  );
}

export function ScheduleForm({ product, done }: { product: Product; done: () => void }) {
  const [frequency, setFrequency] = useState(product.frequency);
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
          <select name="frequency" value={frequency} onChange={e => setFrequency(e.target.value as Product["frequency"])}>
            <option value="daily">日频</option>
            <option value="weekly">周频</option>
            <option value="off">不发送</option>
          </select>
        </Field>
        <Field label="每日接收截止时间">
          <Input key={frequency} name="cutoff" type="time" required readOnly={frequency === "daily"} defaultValue={frequency === "daily" ? "15:00" : product.cutoff} />
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
