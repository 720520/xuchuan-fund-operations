'use client';
import { useState, type ComponentType } from 'react';
import {
  Search,
  Plus,
  ArrowUpRight,
  ChevronRight,
  FileSpreadsheet,
  Mail,
  ShieldCheck,
  Upload,
  ArrowDownToLine,
  Check,
  Clock3,
  CircleAlert,
  FileText,
  History,
  LockKeyhole,
  ArrowRight,
  Users,
  Building2,
  SlidersHorizontal,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { NativeSelect } from '@/components/ui/native-select';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import {
  Table,
  TableHeader,
  TableHead,
  TableBody,
  TableRow,
  TableCell,
} from '@/components/ui/table';
import { Switch } from '@/components/ui/switch';

type Product = {
  name: string;
  code: string;
  share: string;
  nav: string;
  change: string;
  scale: string;
  status: string;
  strategy: string;
  source: string;
  color: string;
};
type Props = {
  view: string;
  readOnly: boolean;
  products: Product[];
  navigate: (id: string) => void;
  notify: (message: string) => void;
  Trend: ComponentType<{ period?: string }>;
  initialProduct: number;
};
function Pill({ text }: { text: string }) {
  return (
    <span
      className={
        'status ' +
        (['待处理', '迟到', '校验异常'].includes(text)
          ? 'amber'
          : text === '反账后'
            ? 'clay'
            : '')
      }
    >
      <i />
      {text}
    </span>
  );
}
function DataTable({
  heads,
  rows,
}: {
  heads: string[];
  rows: React.ReactNode[][];
}) {
  return (
    <Table className="data-table">
      <TableHeader>
        <TableRow>
          {heads.map((h) => (
            <TableHead key={h}>{h}</TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row, i) => (
          <TableRow key={i}>
            {row.map((cell, j) => (
              <TableCell key={j}>{cell}</TableCell>
            ))}
          </TableRow>
        ))}
        {!rows.length && (
          <TableRow>
            <TableCell colSpan={heads.length} className="empty-result">
              暂无匹配结果，试试其他关键词。
            </TableCell>
          </TableRow>
        )}
      </TableBody>
    </Table>
  );
}
function Tabs({
  options,
  value,
  onChange,
}: {
  options: string[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="view-tabs">
      {options.map((o) => (
        <button
          key={o}
          aria-pressed={value === o}
          className={o === value ? 'current' : ''}
          onClick={() => onChange(o)}
        >
          {o}
        </button>
      ))}
    </div>
  );
}
export default function WorkspaceViews({
  view,
  readOnly,
  products,
  navigate,
  notify,
  Trend,
  initialProduct,
}: Props) {
  const [query, setQuery] = useState(''),
    [tab, setTab] = useState('全部产品'),
    [selected, setSelected] = useState(initialProduct),
    [detailTab, setDetailTab] = useState('净值表现'),
    [share, setShare] = useState('A 类份额'),
    [period, setPeriod] = useState('近六月');
  const [modal, setModal] = useState(''),
    [productName, setProductName] = useState(''),
    [newProducts, setNewProducts] = useState<Product[]>([]);
  const [mailIndex, setMailIndex] = useState(0),
    [exception, setException] = useState(0),
    [claimed, setClaimed] = useState<number | null>(null),
    [resolved, setResolved] = useState<number[]>([]),
    [candidate, setCandidate] = useState(1),
    [reason, setReason] = useState('');
  const [files, setFiles] = useState<string[]>([]),
    [parsed, setParsed] = useState(false),
    [uploadTab, setUploadTab] = useState('附件解析'),
    [navValue, setNavValue] = useState(''),
    [navDate, setNavDate] = useState('2026-08-28');
  const [settingTab, setSettingTab] = useState('成员与牌照'),
    [schedule, setSchedule] = useState([true, true, true, false]),
    [frequency, setFrequency] = useState(['日频', '周频', '日频', '不接收']),
    [memberName, setMemberName] = useState(''),
    [members, setMembers] = useState(['林晓', '陈言', '周宁', '许知远']);
  const allProducts = [...products, ...newProducts];
  const p = allProducts[selected] || products[0];
  const openProduct = (i: number) => {
    setSelected(i);
    navigate('detail');
  };
  const titleForMail = [
    '远山稳进一号 — 20260828 估值表及净值',
    '【更正】远山均衡二号 20260828 净值表',
    '远山成长三号 B 类份额净值确认',
  ][mailIndex];
  const exs = [
    {
      name: '远山成长三号',
      type: '净值冲突',
      desc: '同一份额、同一估值日收到两个不同值',
      time: '10:24',
      code: 'YS003 · B 类',
    },
    {
      name: '远山长盈五号',
      type: '解析失败',
      desc: '附件工作表名称与现有模板不一致',
      time: '09:48',
      code: 'YS005 · A 类',
    },
    {
      name: '远山稳进六号',
      type: '未按时收到',
      desc: '超过接收截止时间 11:00',
      time: '11:00',
      code: 'YS006 · A 类',
    },
  ];
  const ex = exs[exception];
  const notification = (message: string) => notify('演示：' + message);
  return (
    <>
      {view === 'products' && (
        <>
          <div className="toolbar">
            <Tabs
              options={['全部产品', '已确认', '待处理', '反账后']}
              value={tab}
              onChange={setTab}
            />
            <Button
              variant="outline"
              disabled={readOnly}
              onClick={() => setModal('新建产品')}
            >
              <Plus />
              新建产品
            </Button>
          </div>
          <section className="panel">
            <div className="list-tools">
              <div className="search-inline">
                <Search size={16} />
                <Input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="搜索产品名称、代码"
                  aria-label="搜索产品"
                />
              </div>
              <span className="subtle">
                {allProducts.length} 只演示产品 · 按牌照归属
              </span>
            </div>
            <DataTable
              heads={[
                '产品名称',
                '策略 / 份额',
                '最新净值',
                '资产规模',
                '接收频率',
                '状态',
                '详情',
              ]}
              rows={allProducts
                .map((r, i) => ({ r, i }))
                .filter(
                  ({ r }) =>
                    (r.name + r.code)
                      .toLowerCase()
                      .includes(query.toLowerCase()) &&
                    (tab === '全部产品' || r.status === tab),
                )
                .map(({ r, i }) => [
                  <button
                    className="product-name"
                    onClick={() => openProduct(i)}
                  >
                    <span
                      className="product-monogram"
                      style={{ color: r.color, background: r.color + '19' }}
                    >
                      {r.name.slice(2, 3)}
                    </span>
                    <span>
                      <strong>{r.name}</strong>
                      <small>{r.code} · 远山私募基金</small>
                    </span>
                  </button>,
                  <span>
                    {r.strategy}
                    <small className="block-sub">{r.share}</small>
                  </span>,
                  <strong className="number">{r.nav}</strong>,
                  r.scale + ' 亿元',
                  i === 1 ? '周频 · 上周五' : '日频',
                  <Pill text={r.status} />,
                  <Button
                    aria-label={'查看' + r.name}
                    variant="ghost"
                    size="icon"
                    onClick={() => openProduct(i)}
                  >
                    <ArrowUpRight />
                  </Button>,
                ])}
            />
            <div className="table-footer">
              展示 {allProducts.length} 只演示产品
              <span>产品可手动创建，也可由附件识别发现</span>
            </div>
          </section>
          <div className="callout">
            <ShieldCheck size={18} />
            <div>
              <strong>同集团可查看，按牌照操作</strong>
              <p>
                切换右上角牌照，可体验跨牌照只读状态。上传、录入与异常处理单独授权。
              </p>
            </div>
          </div>
        </>
      )}
      {view === 'detail' && (
        <>
          <button className="back-link" onClick={() => navigate('products')}>
            产品台账 / <span>{p.name}</span>
          </button>
          <section className="panel detail-identity">
            <div className="identity-left">
              <span
                className="large-monogram"
                style={{ background: p.color + '18', color: p.color }}
              >
                {p.name.slice(2, 3)}
              </span>
              <div>
                <h2>{p.name}私募证券投资基金</h2>
                <p>
                  {p.code} · {p.strategy} · 远山私募基金
                </p>
              </div>
            </div>
            <NativeSelect
              aria-label="选择份额"
              value={share}
              onChange={(e) => setShare(e.target.value)}
            >
              <option>A 类份额</option>
              <option>B 类份额</option>
            </NativeSelect>
            <Pill text="存续中" />
          </section>
          <div className="detail-metrics">
            <div>
              <span>单位净值 · {share}</span>
              <strong>{share === 'A 类份额' ? p.nav : '1.1728'}</strong>
              <small className="positive">日变动 {p.change}</small>
            </div>
            <div>
              <span>资产规模</span>
              <strong>
                {p.scale}
                <small>亿元</small>
              </strong>
              <small>估值表提取 · 演示</small>
            </div>
            <div>
              <span>区间收益</span>
              <strong>
                +18.62<small>%</small>
              </strong>
              <small>演示指标，口径待核验</small>
            </div>
            <div>
              <span>最大回撤</span>
              <strong>
                −3.24<small>%</small>
              </strong>
              <small>演示指标，口径待核验</small>
            </div>
          </div>
          <Tabs
            options={['净值表现', '持仓与现金', '关联资料', '操作动态']}
            value={detailTab}
            onChange={setDetailTab}
          />
          {detailTab === '净值表现' ? (
            <section className="panel">
              <div className="panel-header">
                <div>
                  <h2>净值历史</h2>
                  <p>估值截至 2026.08.28 · 更新于 2026.08.31 09:32</p>
                </div>
                <Tabs
                  options={['近一月', '近三月', '近六月']}
                  value={period}
                  onChange={setPeriod}
                />
              </div>
              <Trend period={period} />
              <DataTable
                heads={[
                  '估值日期',
                  '份额',
                  '有效净值',
                  '更新日期',
                  '状态',
                  '来源',
                ]}
                rows={['08.28', '08.27', '08.26'].map((d, i) => [
                  '2026.' + d,
                  share,
                  i === 0 ? p.nav : i === 1 ? '1.1824' : '1.1796',
                  i === 0 ? '08.31 09:32' : '08.28 09:15',
                  <Pill text={i === 0 ? '反账后' : '已确认'} />,
                  <Button
                    variant="ghost"
                    onClick={() => setModal(i === 0 ? '反账版本' : '原始来源')}
                  >
                    {i === 0 ? '版本对照' : '查看原件'}
                    <ArrowUpRight size={13} />
                  </Button>,
                ])}
              />
            </section>
          ) : detailTab === '持仓与现金' ? (
            <section className="panel">
              <div className="holding-summary">
                <div>
                  <span>权益仓位</span>
                  <strong>72.6%</strong>
                </div>
                <div>
                  <span>现金及等价物</span>
                  <strong>18.4%</strong>
                </div>
                <div>
                  <span>其他资产</span>
                  <strong>9.0%</strong>
                </div>
              </div>
              <div className="allocation">
                <i style={{ width: '72.6%', background: '#879478' }} />
                <i style={{ width: '18.4%', background: '#c8b697' }} />
                <i style={{ width: '9%', background: '#dedbd0' }} />
              </div>
              <DataTable
                heads={[
                  '资产 / 标的',
                  '数量',
                  '估值市值',
                  '净资产占比',
                  '数据来源',
                ]}
                rows={[
                  '示例证券 A',
                  '示例证券 B',
                  '示例证券 C',
                  '现金及等价物',
                ].map((n, i) => [
                  n,
                  i === 3 ? '—' : (100000 * (i + 1)).toLocaleString(),
                  ['28,600,000', '22,880,000', '17,160,000', '52,624,000'][i],
                  ['10.0%', '8.0%', '6.0%', '18.4%'][i],
                  <span className="source-link">
                    <FileSpreadsheet size={14} />
                    估值表 · 模拟
                  </span>,
                ])}
              />
            </section>
          ) : detailTab === '关联资料' ? (
            <section className="panel">
              <DataTable
                heads={['文件名称', '类型', '来源', '归档时间', '操作']}
                rows={[
                  '估值表_20260828.xlsx',
                  '净值确认表_20260828.pdf',
                  '反账说明_20260831.pdf',
                ].map((f, i) => [
                  <span className="source-link">
                    <FileSpreadsheet size={17} />
                    {f}
                  </span>,
                  i === 2 ? '反账材料' : '托管材料',
                  '托管邮件',
                  '2026.08.31 09:32',
                  <Button variant="ghost" onClick={() => setModal('原始来源')}>
                    查看原件
                    <ArrowUpRight size={13} />
                  </Button>,
                ])}
              />
            </section>
          ) : (
            <section className="panel timeline-panel">
              {[
                '运营 林晓标注反账，并确认新版本生效',
                '系统归档托管邮件及附件',
                '系统完成份额匹配与数据校验',
                '管理员创建产品接收配置',
              ].map((t, i) => (
                <div className="timeline-item" key={t}>
                  <i />
                  <div>
                    <strong>{t}</strong>
                    <p>
                      2026.08.31 {['09:32', '09:29', '09:28', '08:50'][i]} ·
                      演示记录
                    </p>
                  </div>
                </div>
              ))}
            </section>
          )}
        </>
      )}
      {view === 'nav' && (
        <>
          <div className="toolbar">
            <Tabs
              options={['全部产品', '已确认', '待处理', '反账后']}
              value={tab}
              onChange={setTab}
            />
            <Button
              variant="outline"
              disabled={readOnly}
              onClick={() => {
                navigate('upload');
                setUploadTab('人工录入');
              }}
            >
              <Plus />
              人工录入
            </Button>
          </div>
          <div className="inline-summary">
            <span>
              <i className="dot green" />9 条已确认
            </span>
            <span>
              <i className="dot amber-dot" />3 条待处理
            </span>
            <span>估值日与接收日期分开记录</span>
          </div>
          <section className="panel">
            <div className="list-tools">
              <div className="search-inline">
                <Search size={16} />
                <Input
                  aria-label="搜索净值"
                  placeholder="搜索产品或份额"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
              </div>
              <Input
                aria-label="筛选估值日期"
                type="date"
                value={navDate}
                onChange={(e) => setNavDate(e.target.value)}
                className="date-input"
              />
            </div>
            <DataTable
              heads={[
                '产品 / 份额',
                '估值日期',
                '单位净值',
                '累计净值',
                '份额总数',
                '状态',
                '来源',
              ]}
              rows={
                navDate === '2026-08-28'
                  ? products
                      .filter(
                        (r) =>
                          r.name.includes(query) &&
                          (tab === '全部产品' || r.status === tab),
                      )
                      .map((r) => [
                        <button
                          className="product-name"
                          onClick={() => openProduct(products.indexOf(r))}
                        >
                          <span>
                            <strong>{r.name}</strong>
                            <small>
                              {r.code} · {r.share}
                            </small>
                          </span>
                        </button>,
                        navDate,
                        r.nav,
                        (Number(r.nav) + 0.1).toFixed(4),
                        '240,000,000.00',
                        <Pill text={r.status} />,
                        <Button
                          variant="ghost"
                          onClick={() =>
                            setModal(
                              r.status === '反账后' ? '反账版本' : '原始来源',
                            )
                          }
                        >
                          <FileSpreadsheet size={15} />
                          {r.status === '反账后' ? '查看版本' : '邮件附件'}
                        </Button>,
                      ])
                  : []
              }
            />
            <div className="table-footer">
              数据来源：托管邮件 / 运营上传 / 人工录入
              <span>仅含 2026.08.28 演示数据</span>
            </div>
          </section>
        </>
      )}
      {view === 'mail' && (
        <>
          <div className="inline-summary">
            <span>
              <ShieldCheck size={14} />
              原始邮件只读归档，不可删除
            </span>
            <span>邮箱状态：未连接 · 当前为模拟收件箱</span>
          </div>
          <section className="panel mail-layout">
            <div className="mail-list">
              <div className="search-inline">
                <Search size={15} />
                <Input
                  aria-label="搜索邮件"
                  placeholder="搜索主题、托管机构"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
              </div>
              {['远山稳进一号', '远山均衡二号', '远山成长三号'].map(
                (n, i) =>
                  n.includes(query) && (
                    <button
                      key={n}
                      className={
                        'mail-item ' + (mailIndex === i ? 'chosen' : '')
                      }
                      onClick={() => setMailIndex(i)}
                    >
                      <div>
                        <strong>托管机构 {i === 1 ? 'B' : 'A'}</strong>
                        <small>{['09:32', '09:18', '08:56'][i]}</small>
                      </div>
                      <h3>
                        {i === 1 ? '【更正】' : ''}
                        {n}净值材料
                      </h3>
                      <p>估值日期 2026-08-28，详见附件。</p>
                      <span>
                        <FileSpreadsheet size={12} />2 个附件{' '}
                        <Pill text={i === 1 ? '反账后' : '已归档'} />
                      </span>
                    </button>
                  ),
              )}
              {!['远山稳进一号', '远山均衡二号', '远山成长三号'].some((n) =>
                n.includes(query),
              ) && <p className="empty-result">没有匹配邮件</p>}
              <div className="mail-storage">
                <LockKeyhole size={13} />
                原件保留，所有查看可追溯
              </div>
            </div>
            <article className="mail-body">
              <div className="mail-heading">
                <span className="eyebrow">ARCHIVED MAIL · 演示邮件</span>
                <Button
                  variant="outline"
                  onClick={() =>
                    notification('原始邮件下载尚未接入，不会下载真实邮件。')
                  }
                >
                  <ArrowDownToLine />
                  下载原件
                </Button>
              </div>
              <h2>{titleForMail}</h2>
              <dl className="mail-meta">
                <dt>发件人</dt>
                <dd>托管估值服务 &lt;valuation@example.com&gt;</dd>
                <dt>收件人</dt>
                <dd>运营公共邮箱 &lt;operations@example.com&gt;</dd>
                <dt>接收时间</dt>
                <dd>2026 年 8 月 31 日 09:32</dd>
                <dt>关联产品</dt>
                <dd>
                  {products[mailIndex].name} · {products[mailIndex].share}
                </dd>
              </dl>
              <div className="letter">
                <p>尊敬的管理人：</p>
                <p>
                  您好，附件为贵司产品 2026 年 8 月 28
                  日估值表及净值确认表，请查收。
                </p>
                <p>如有疑问，请与估值服务团队联系。</p>
                <p className="subtle">
                  托管估值服务团队
                  <br />
                  本邮件为界面设计样本，不对应真实机构。
                </p>
              </div>
              <h3 className="attachments-title">
                附件 <span>2</span>
              </h3>
              <div className="attachment-grid">
                {['估值表_20260828.xlsx', '净值确认表_20260828.pdf'].map(
                  (f, i) => (
                    <button
                      className="attachment"
                      key={f}
                      onClick={() => setModal('原始来源')}
                    >
                      <span className="file-icon">
                        <FileSpreadsheet size={22} />
                      </span>
                      <span>
                        <strong>{f}</strong>
                        <small>{i ? '186' : '428'} KB · 已归档</small>
                      </span>
                      <ArrowUpRight size={15} />
                    </button>
                  ),
                )}
              </div>
              <div className="callout compact-callout">
                <Check size={17} />
                <span>已匹配产品与份额，原始附件可追溯至有效数据。</span>
              </div>
            </article>
          </section>
        </>
      )}
      {view === 'exceptions' && (
        <>
          <div className="exception-stats">
            <div>
              <span>待处理</span>
              <strong>{3 - resolved.length}</strong>
            </div>
            <div>
              <span>处理中</span>
              <strong>{claimed === null ? 0 : 1}</strong>
            </div>
            <div>
              <span>已完成 · 本次演示</span>
              <strong>{resolved.length}</strong>
            </div>
            <p>
              <Users size={15} />
              牌照共享待办 · 无需预先分配
            </p>
          </div>
          <section className="panel exception-layout">
            <div className="exception-list">
              {exs.map((e, i) => (
                <button
                  key={e.name}
                  className={
                    'exception-item ' + (exception === i ? 'chosen' : '')
                  }
                  onClick={() => {
                    setException(i);
                    setReason('');
                  }}
                >
                  <div>
                    <span className="exception-kind">
                      {resolved.includes(i) ? '已处理' : e.type}
                    </span>
                    <small>{e.time}</small>
                  </div>
                  <strong>{e.name}</strong>
                  <p>{e.desc}</p>
                  <small>{e.code} · 2026.08.28</small>
                </button>
              ))}
            </div>
            <article className="exception-body">
              <div className="panel-title-row">
                <div>
                  <div className="eyebrow">EXCEPTION · 0{exception + 1}</div>
                  <h2>{ex.type}</h2>
                </div>
                <Pill
                  text={
                    resolved.includes(exception)
                      ? '已处理'
                      : claimed === exception
                        ? '处理中'
                        : '待处理'
                  }
                />
              </div>
              <p className="exception-intro">
                {ex.name} · {ex.code} · 估值日期 2026.08.28
              </p>
              <div className="callout compact-callout">
                <CircleAlert size={17} />
                <span>{ex.desc}。原始记录将始终保留。</span>
              </div>
              {exception === 0 ? (
                <>
                  <h3 className="section-label">选择有效记录</h3>
                  <div className="candidate-grid">
                    {['1.2518', '1.2546'].map((v, i) => (
                      <button
                        key={v}
                        disabled={readOnly || resolved.includes(0)}
                        className={
                          'candidate ' + (candidate === i ? 'picked' : '')
                        }
                        onClick={() => setCandidate(i)}
                      >
                        <span>
                          候选记录 0{i + 1}
                          <i>{candidate === i && <Check size={12} />}</i>
                        </span>
                        <strong>{v}</strong>
                        <p>托管机构 A · {i ? '10:24' : '09:16'} 收到</p>
                        <small>
                          {i ? '净值确认表_更正.xlsx' : '净值确认表.xlsx'}
                        </small>
                      </button>
                    ))}
                  </div>
                  <p className="subtle">
                    选择后更新有效版本；另一条记录保留用于追溯。
                  </p>
                </>
              ) : (
                <div className="exception-remedy">
                  <FileSpreadsheet size={28} />
                  <h3>
                    {exception === 1
                      ? '需要重新解析或补录数据'
                      : '等待对应材料到达'}
                  </h3>
                  <p>
                    {exception === 1
                      ? '正式系统将支持重试解析、补齐数据并重新校验。'
                      : '材料到达并匹配预期后，系统自动解除未收到状态。'}
                  </p>
                  <Button
                    variant="outline"
                    disabled={readOnly}
                    onClick={() => navigate('upload')}
                  >
                    前往上传与解析
                    <ArrowRight size={14} />
                  </Button>
                </div>
              )}
              <label className="field-label">
                处理说明
                <Input
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  disabled={readOnly || resolved.includes(exception)}
                  placeholder="记录本次处理依据（演示可选）"
                />
              </label>
              <div className="exception-actions">
                {claimed === exception && (
                  <Button
                    variant="outline"
                    onClick={() => {
                      setClaimed(null);
                      notification('待办已释放，可由其他有权限的运营接手。');
                    }}
                  >
                    释放待办
                  </Button>
                )}
                <Button
                  disabled={
                    readOnly ||
                    resolved.includes(exception) ||
                    (claimed !== null && claimed !== exception)
                  }
                  onClick={() => {
                    if (claimed !== exception) {
                      setClaimed(exception);
                      notification('已由林晓开始处理，当前待办已占用。');
                    } else if (exception === 0) {
                      setResolved([...resolved, exception]);
                      setClaimed(null);
                      notification(
                        `已选定 ${candidate === 0 ? '1.2518' : '1.2546'} 为有效净值，保留全部候选记录。`,
                      );
                    } else
                      notification('需完成补传或重新解析，不能直接关闭异常。');
                  }}
                >
                  {resolved.includes(exception)
                    ? '已完成'
                    : claimed === exception
                      ? exception === 0
                        ? '确认有效记录'
                        : '检查完成条件'
                      : '开始处理'}
                  <ArrowRight size={14} />
                </Button>
              </div>
              <div className="audit-note">
                <ShieldCheck size={14} />
                操作人、时间与处理结果将记录 · 当前仅模拟，不持久保存
              </div>
            </article>
          </section>
        </>
      )}
      {view === 'upload' && (
        <>
          <Tabs
            options={['附件解析', '人工录入']}
            value={uploadTab}
            onChange={setUploadTab}
          />
          <div className="upload-layout">
            <section className="panel upload-panel">
              <div className="panel-header">
                <div>
                  <h2>
                    {uploadTab === '附件解析'
                      ? '让资料，成为可用的数据。'
                      : '补充一条净值记录'}
                  </h2>
                  <p>
                    {uploadTab === '附件解析'
                      ? '历史资料与新增附件，都从这里开始。'
                      : '来源记录为当前运营账户，不要求另一人复核。'}
                  </p>
                </div>
              </div>
              {uploadTab === '附件解析' ? (
                <>
                  <label className={'dropzone ' + (readOnly ? 'disabled' : '')}>
                    <span className="upload-orb">
                      <Upload size={27} strokeWidth={1.4} />
                    </span>
                    <strong>
                      {files.length
                        ? `已选择 ${files.length} 个文件`
                        : '选择需要解析的附件'}
                    </strong>
                    <p>Excel、PDF、CSV · 仅本地文件名演示</p>
                    <span className="upload-browse">
                      浏览文件 <Plus size={13} />
                    </span>
                    <Input
                      type="file"
                      multiple
                      accept=".xlsx,.xls,.pdf,.csv"
                      disabled={readOnly}
                      aria-label="选择演示附件"
                      onChange={(e) => {
                        setFiles(
                          Array.from(e.target.files || []).map((f) => f.name),
                        );
                        setParsed(false);
                      }}
                    />
                  </label>
                  <p className="local-disclaimer">
                    <LockKeyhole size={13} />
                    原型不读取文件内容，不上传至服务器，不执行真实解析。
                  </p>
                  {files.length > 0 && (
                    <div className="selected-files">
                      {files.map((f, i) => (
                        <div key={i}>
                          <FileSpreadsheet size={17} />
                          <span>{f}</span>
                          <Pill text={parsed ? '演示完成' : '待模拟'} />
                        </div>
                      ))}
                    </div>
                  )}
                  <div className="upload-bottom">
                    <Button
                      variant="outline"
                      disabled={readOnly}
                      onClick={() => {
                        setFiles(['估值表_演示样本.xlsx']);
                        setParsed(false);
                      }}
                    >
                      使用演示样本
                    </Button>
                    <Button
                      disabled={readOnly || !files.length}
                      onClick={() => {
                        setParsed(true);
                        notification(
                          '已展示模拟解析结果，未处理所选文件内容。',
                        );
                      }}
                    >
                      预览解析结果
                      <ArrowRight size={14} />
                    </Button>
                  </div>
                  {parsed && (
                    <div className="parse-result">
                      <Check size={20} />
                      <div>
                        <strong>模拟识别完成 · 1 条演示记录</strong>
                        <p>
                          远山稳进一号 / A 类 · 2026.08.28 · 单位净值 1.1862
                        </p>
                        <small>此结果固定用于展示，不来自所选文件。</small>
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <form
                  className="manual-form"
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (!readOnly)
                      notification('净值已模拟提交，来源为林晓；刷新后重置。');
                  }}
                >
                  <label className="field-label">
                    所属产品
                    <NativeSelect required aria-label="所属产品">
                      {products.map((r) => (
                        <option key={r.code}>{r.name}</option>
                      ))}
                    </NativeSelect>
                  </label>
                  <div className="form-grid">
                    <label className="field-label">
                      份额类别
                      <NativeSelect required aria-label="份额类别">
                        <option>A 类</option>
                        <option>B 类</option>
                      </NativeSelect>
                    </label>
                    <label className="field-label">
                      估值日期
                      <Input
                        required
                        type="date"
                        value={navDate}
                        onChange={(e) => setNavDate(e.target.value)}
                      />
                    </label>
                  </div>
                  <label className="field-label">
                    单位净值
                    <Input
                      required
                      type="number"
                      step="0.0001"
                      min="0.0001"
                      placeholder="例如 1.1862"
                      value={navValue}
                      onChange={(e) => setNavValue(e.target.value)}
                    />
                  </label>
                  <div className="callout compact-callout">
                    <ShieldCheck size={16} />
                    <span>录入来源：林晓 / 远山牌照运营账户</span>
                  </div>
                  <Button type="submit" disabled={readOnly}>
                    模拟提交
                    <ArrowRight size={14} />
                  </Button>
                </form>
              )}
            </section>
            <aside className="upload-guide">
              <span className="eyebrow">A CLEAR PATH</span>
              <h2>每一步，都有依据。</h2>
              {[
                ['01', '识别归属', '匹配管理人、产品与份额，避免跨牌照关联。'],
                [
                  '02',
                  '提取与校验',
                  '按托管模板解析，正常数据通过规则后自动确认。',
                ],
                [
                  '03',
                  '异常交给人',
                  '无法识别或发生冲突，进入牌照共享异常中心。',
                ],
                [
                  '04',
                  '原件始终保留',
                  '接收日期不替代估值日期，历史文件与记录可追溯。',
                ],
              ].map(([n, t, d]) => (
                <div className="guide-step" key={n}>
                  <span>{n}</span>
                  <div>
                    <strong>{t}</strong>
                    <p>{d}</p>
                  </div>
                </div>
              ))}
            </aside>
          </div>
        </>
      )}
      {view === 'settings' && (
        <>
          <div className="settings-banner">
            <Building2 size={25} />
            <div>
              <h2>远山集团</h2>
              <p>2 个管理人牌照 · 一个账户，多份独立授权</p>
            </div>
            <span className="preview-tag">管理员视图演示</span>
          </div>
          <Tabs
            options={['成员与牌照', '接收配置', '权限原则']}
            value={settingTab}
            onChange={setSettingTab}
          />
          {settingTab === '成员与牌照' ? (
            <section className="panel">
              <div className="panel-header padded-bottom">
                <h2>成员管理</h2>
                <Button
                  disabled={readOnly}
                  onClick={() => setModal('添加成员')}
                >
                  <Plus />
                  添加成员
                </Button>
              </div>
              <DataTable
                heads={['成员', '远山牌照', '知行牌照', '状态', '管理']}
                rows={members.map((m, i) => [
                  <span className="member">
                    <span className="avatar">{m.slice(0, 1)}</span>
                    {m}
                  </span>,
                  i === 0
                    ? '运营 · 可操作'
                    : i === 1
                      ? '基金经理 · 指定产品'
                      : i === 2
                        ? '运营负责人'
                        : '管理层 · 查看',
                  i === 0 ? '集团只读' : i === 2 ? '运营 · 可操作' : '未加入',
                  <Pill text="正常" />,
                  <Button
                    variant="ghost"
                    disabled={readOnly}
                    onClick={() =>
                      notification(
                        `${m} 的授权面板仅作展示，尚未连接真实账户管理。`,
                      )
                    }
                  >
                    管理授权
                    <ChevronRight size={14} />
                  </Button>,
                ])}
              />
              <div className="table-footer">
                系统管理员维护账户与授权
                <span>技术管理权限不自动包含业务修改权限</span>
              </div>
            </section>
          ) : settingTab === '接收配置' ? (
            <section className="panel">
              <div className="panel-header padded-bottom">
                <div>
                  <h2>产品接收预期</h2>
                  <p>管理员决定哪些产品预期发送，以及发送频率。</p>
                </div>
              </div>
              <DataTable
                heads={['产品', '预期接收', '频率', '默认对应日期', '截止时间']}
                rows={products.map((r, i) => [
                  r.name,
                  <Switch
                    aria-label={r.name + '预期接收'}
                    checked={schedule[i]}
                    disabled={readOnly}
                    onCheckedChange={(v) =>
                      setSchedule(schedule.map((s, j) => (i === j ? v : s)))
                    }
                  />,
                  <NativeSelect
                    aria-label={r.name + '接收频率'}
                    disabled={readOnly || !schedule[i]}
                    value={frequency[i]}
                    onChange={(e) =>
                      setFrequency(
                        frequency.map((f, j) => (i === j ? e.target.value : f)),
                      )
                    }
                  >
                    <option>日频</option>
                    <option>周频</option>
                    <option>不接收</option>
                  </NativeSelect>,
                  frequency[i] === '周频'
                    ? '上周五 · 可手选'
                    : '依托管估值日期',
                  <Input
                    type="time"
                    aria-label={r.name + '截止时间'}
                    defaultValue="11:00"
                    disabled={readOnly || !schedule[i]}
                    className="time-input"
                  />,
                ])}
              />
              <div className="upload-bottom">
                <span className="subtle">以上配置只在当前演示会话中生效。</span>
                <Button
                  disabled={readOnly}
                  onClick={() => notification('接收配置已模拟保存。')}
                >
                  保存配置
                </Button>
              </div>
            </section>
          ) : (
            <section className="panel permission-cards">
              {[
                ['查看按集团', '同集团运营可查看各牌照产品详情。'],
                ['操作按牌照', '加入牌照并获得动作授权后，才可处理业务。'],
                ['敏感信息独立授权', '查看、修改、下载权限分别配置。'],
                [
                  '每次操作记录个人',
                  '不共享运营账户，兼任岗位也保留真实操作人。',
                ],
              ].map(([t, d]) => (
                <article key={t}>
                  <ShieldCheck size={22} />
                  <h3>{t}</h3>
                  <p>{d}</p>
                </article>
              ))}
            </section>
          )}
        </>
      )}
      <Dialog
        open={!!modal}
        onOpenChange={(v) => {
          if (!v) setModal('');
        }}
      >
        <DialogContent className="prototype-dialog">
          <DialogHeader>
            <DialogTitle>{modal}</DialogTitle>
            <DialogDescription>界面交互演示 · 无真实数据写入</DialogDescription>
          </DialogHeader>
          {modal === '新建产品' ? (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (readOnly) return;
                setNewProducts([
                  ...newProducts,
                  {
                    ...products[0],
                    name: productName,
                    code: 'DEMO' + (newProducts.length + 1),
                    nav: '—',
                    scale: '—',
                    change: '—',
                    status: '待处理',
                  },
                ]);
                setModal('');
                setProductName('');
                notification('产品已添加至演示列表，刷新后重置。');
              }}
            >
              <label className="field-label">
                产品名称
                <Input
                  required
                  value={productName}
                  onChange={(e) => setProductName(e.target.value)}
                  placeholder="输入产品简称"
                  maxLength={30}
                />
              </label>
              <label className="field-label">
                所属牌照
                <Input readOnly value="远山私募基金" />
              </label>
              <p className="form-note">
                邮箱识别的新产品确认机制仍待业务确定。本表单仅演示人工创建。
              </p>
              <Button type="submit" disabled={readOnly}>
                创建演示产品
              </Button>
            </form>
          ) : modal === '添加成员' ? (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (readOnly) return;
                setMembers([...members, memberName]);
                setMemberName('');
                setModal('');
                notification('成员已加入演示列表，未开通实际账户。');
              }}
            >
              <label className="field-label">
                成员姓名
                <Input
                  required
                  value={memberName}
                  onChange={(e) => setMemberName(e.target.value)}
                  maxLength={20}
                />
              </label>
              <label className="field-label">
                牌照
                <NativeSelect aria-label="新成员牌照">
                  <option>远山私募基金</option>
                </NativeSelect>
              </label>
              <Button type="submit" disabled={readOnly}>
                添加演示成员
              </Button>
            </form>
          ) : modal === '反账版本' ? (
            <>
              <div className="callout compact-callout">
                <History size={19} />
                <span>估值日期 08.28 · 于 08.31 收到反账更新</span>
              </div>
              <div className="version-row">
                <span>原始记录 · 保留追溯</span>
                <strong>1.0896</strong>
              </div>
              <div className="version-row current-version">
                <span>反账后 · 当前有效</span>
                <strong>1.0928</strong>
              </div>
              <p className="form-note">
                历史曲线采用反账后的有效值，原始记录不删除。演示操作人：林晓 ·
                2026.08.31 09:32
              </p>
            </>
          ) : (
            <>
              <div className="document-sample">
                <FileSpreadsheet size={36} />
                <h3>托管估值资料 · 演示原件</h3>
                <p>这里只展示来源关系，不包含真实附件内容。</p>
              </div>
              <dl className="mail-meta">
                <dt>来源</dt>
                <dd>托管邮件 / 2026.08.31</dd>
                <dt>估值日期</dt>
                <dd>2026.08.28</dd>
                <dt>归档状态</dt>
                <dd>原始邮件不可删除</dd>
              </dl>
              <Button
                variant="outline"
                onClick={() => {
                  setModal('');
                  navigate('mail');
                }}
              >
                进入邮件归档
                <ArrowRight size={14} />
              </Button>
            </>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
