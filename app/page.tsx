'use client';
import { useEffect, useState } from 'react';
import WorkspaceViews from './workspace-views';
import {
  LayoutDashboard,
  Layers3,
  ChartNoAxesCombined,
  Mail,
  CircleAlert,
  Upload,
  Settings2,
  ChevronRight,
  ArrowUpRight,
  Plus,
  ShieldCheck,
  PanelLeftClose,
  Menu,
  Check,
  ArrowRight,
  LockKeyhole,
  Building2,
  X,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { NativeSelect } from '@/components/ui/native-select';
import {
  Table,
  TableHeader,
  TableHead,
  TableBody,
  TableRow,
  TableCell,
} from '@/components/ui/table';
import { ChartContainer } from '@/components/ui/chart';
import {
  AreaChart,
  Area,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
} from 'recharts';

const links = [
  { id: 'overview', label: '工作概览', icon: LayoutDashboard },
  { id: 'products', label: '产品台账', icon: Layers3 },
  { id: 'nav', label: '净值与估值', icon: ChartNoAxesCombined },
  { id: 'mail', label: '邮件归档', icon: Mail },
  { id: 'exceptions', label: '异常中心', icon: CircleAlert },
  { id: 'upload', label: '上传与解析', icon: Upload },
  { id: 'settings', label: '组织与权限', icon: Settings2 },
];
export const products = [
  {
    name: '远山稳进一号',
    code: 'YS001',
    share: 'A 类',
    nav: '1.1862',
    change: '+0.32%',
    scale: '2.86',
    status: '已确认',
    strategy: '量化多头',
    source: '托管机构 A',
    color: '#788b79',
  },
  {
    name: '远山均衡二号',
    code: 'YS002',
    share: 'A 类',
    nav: '1.0928',
    change: '+0.18%',
    scale: '1.74',
    status: '反账后',
    strategy: '市场中性',
    source: '托管机构 B',
    color: '#a38d72',
  },
  {
    name: '远山成长三号',
    code: 'YS003',
    share: 'B 类',
    nav: '1.2546',
    change: '+0.56%',
    scale: '3.12',
    status: '待处理',
    strategy: '主观多头',
    source: '托管机构 A',
    color: '#918aa1',
  },
  {
    name: '远山长盈五号',
    code: 'YS005',
    share: 'A 类',
    nav: '1.0635',
    change: '−0.12%',
    scale: '1.38',
    status: '已确认',
    strategy: '固收增强',
    source: '托管机构 C',
    color: '#8399a0',
  },
];
const trend = Array.from({ length: 33 }, (_, i) => ({
  day:
    i === 0
      ? '03.02'
      : i === 8
        ? '04.15'
        : i === 16
          ? '05.29'
          : i === 24
            ? '07.13'
            : i === 32
              ? '08.28'
              : '',
  value: +(
    1.01 +
    i * 0.0047 +
    Math.sin(i * 1.23) * 0.009 +
    Math.cos(i * 0.52) * 0.012
  ).toFixed(4),
  base: +(1.015 + i * 0.0016 + Math.sin(i * 0.7) * 0.005).toFixed(4),
}));
export function Status({ children }: { children: React.ReactNode }) {
  return (
    <span
      className={
        'status ' +
        (children === '待处理' || children === '迟到'
          ? 'amber'
          : children === '反账后'
            ? 'clay'
            : '')
      }
    >
      <i />
      {children}
    </span>
  );
}
export function Trend({ period = '近六月' }: { period?: string }) {
  const data =
    period === '近一月'
      ? trend.slice(-8)
      : period === '近三月'
        ? trend.slice(-16)
        : trend;
  return (
    <ChartContainer
      config={{
        value: { label: '产品单位净值', color: '#a96349' },
        base: { label: '对比产品', color: '#aca99f' },
      }}
      className="trend"
    >
      <AreaChart
        data={data}
        margin={{ left: -23, right: 8, top: 14, bottom: 0 }}
        accessibilityLayer
      >
        <defs>
          <linearGradient id="chartFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#bd8067" stopOpacity={0.18} />
            <stop offset="100%" stopColor="#bd8067" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid
          vertical={false}
          strokeDasharray="3 5"
          stroke="#e7e5df"
        />
        <XAxis
          dataKey="day"
          axisLine={false}
          tickLine={false}
          tick={{ fontSize: 10, fill: '#89877f' }}
          interval={0}
        />
        <YAxis
          domain={[1, 1.2]}
          ticks={[1, 1.05, 1.1, 1.15, 1.2]}
          axisLine={false}
          tickLine={false}
          tick={{ fontSize: 10, fill: '#89877f' }}
          tickFormatter={(v) => v.toFixed(2)}
        />
        <Tooltip
          formatter={(v) => Number(v).toFixed(4)}
          contentStyle={{
            borderRadius: 10,
            border: '1px solid #e4e1d8',
            fontSize: 12,
          }}
        />
        <Area
          type="monotone"
          name="对比产品"
          dataKey="base"
          fill="none"
          stroke="#b6b6a8"
          strokeDasharray="4 4"
          strokeWidth={1.5}
          isAnimationActive={false}
        />
        <Area
          type="monotone"
          name="单位净值"
          dataKey="value"
          fill="url(#chartFill)"
          stroke="#aa664e"
          strokeWidth={2.5}
          isAnimationActive={false}
        />
      </AreaChart>
    </ChartContainer>
  );
}

export default function Home() {
  const [view, setView] = useState('overview'),
    [license, setLicense] = useState('远山私募基金'),
    [menu, setMenu] = useState(false),
    [period, setPeriod] = useState('近六月'),
    [productIndex, setProductIndex] = useState(0),
    [toast, setToast] = useState('');
  const readOnly = license === '知行私募基金';
  useEffect(() => {
    const v = new URLSearchParams(location.search).get('view');
    if (v && [...links.map((l) => l.id), 'detail'].includes(v)) setView(v);
  }, []);
  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(''), 3500);
    return () => clearTimeout(id);
  }, [toast]);
  const navigate = (id: string) => {
    setView(id);
    setMenu(false);
    window.history.replaceState(null, '', `?view=${id}`);
  };
  const title = links.find((l) => l.id === view)?.label || '产品详情';
  return (
    <div className="app-shell">
      <aside className={'sidebar ' + (menu ? 'is-open' : '')}>
        <a className="brand" href="/?view=overview">
          <span className="brand-icon">
            <Layers3 size={22} strokeWidth={1.4} />
          </span>
          <span>
            序川<span className="brand-sub">基金运营工作台</span>
          </span>
        </a>
        <div className="workspace">
          <span className="workspace-icon">远</span>
          <div>
            <strong>远山集团</strong>
            <small>集团协作空间 · 演示</small>
          </div>
          <Button
            variant="ghost"
            size="icon"
            aria-label="收起导航"
            onClick={() => setMenu(false)}
          >
            <PanelLeftClose size={15} />
          </Button>
        </div>
        <div className="nav-label">工作空间</div>
        <nav aria-label="主导航">
          {links.slice(0, 6).map((l) => (
            <button
              key={l.id}
              className={
                'nav-link ' +
                (view === l.id || (view === 'detail' && l.id === 'products')
                  ? 'active'
                  : '')
              }
              onClick={() => navigate(l.id)}
            >
              <l.icon size={18} strokeWidth={1.6} />
              <span>{l.label}</span>
              {l.id === 'exceptions' && <span className="nav-count">3</span>}
            </button>
          ))}
        </nav>
        <div className="nav-label second">管理</div>
        <button
          className={'nav-link ' + (view === 'settings' ? 'active' : '')}
          onClick={() => navigate('settings')}
        >
          <Settings2 size={18} strokeWidth={1.6} />
          <span>组织与权限</span>
        </button>
        <div className="sidebar-bottom">
          <a className="gallery-link" href="/prototype/index.html">
            <Layers3 size={15} />
            全部页面预览
            <ArrowUpRight size={14} />
          </a>
          <div className="sync-note">
            <i />
            演示工作区 · 未连接邮箱
          </div>
          <div className="user">
            <span className="avatar">林</span>
            <div>
              <strong>林晓</strong>
              <small>运营 · 远山牌照可操作</small>
            </div>
            <ShieldCheck size={17} />
          </div>
        </div>
      </aside>
      {menu && (
        <button
          className="mobile-backdrop"
          aria-label="关闭菜单"
          onClick={() => setMenu(false)}
        />
      )}
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            <Button
              className="mobile-menu"
              variant="ghost"
              size="icon"
              aria-label="打开导航"
              onClick={() => setMenu(true)}
            >
              <Menu />
            </Button>
            <span>工作空间</span>
            <ChevronRight size={12} />
            <strong>{title}</strong>
          </div>
          <div className="top-actions">
            <span className="preview-tag">设计预览 · 模拟数据</span>
            <Building2 size={15} />
            <NativeSelect
              aria-label="当前管理人牌照"
              value={license}
              onChange={(e) => setLicense(e.target.value)}
            >
              <option>远山私募基金</option>
              <option>知行私募基金</option>
            </NativeSelect>
          </div>
        </header>
        {readOnly && (
          <div className="readonly">
            <LockKeyhole size={15} />
            知行牌照只读视角 ·
            仅演示权限状态，仍使用同一组虚构样本；操作需管理员授权。
          </div>
        )}
        <main className="page-content">
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                {view === 'overview'
                  ? 'MONDAY, AUGUST 31, 2026'
                  : 'YUANSHAN · FUND OPERATIONS'}
              </div>
              <h1>{view === 'overview' ? '从容开启，今日运营。' : title}</h1>
              <p>
                {view === 'overview'
                  ? '每一次更新，清晰可循。这里是你的产品与今日进展。'
                  : '在同一个工作空间，让业务数据与原始依据始终相连。'}
              </p>
            </div>
            <Button
              className="primary-action"
              disabled={readOnly}
              onClick={() => navigate('upload')}
            >
              <Plus size={16} />
              上传资料
            </Button>
          </div>
          {view === 'overview' ? (
            <>
              <div className="metrics">
                <div>
                  <span>存续产品</span>
                  <strong>
                    12 <small>只</small>
                  </strong>
                  <p>当前牌照管理产品</p>
                </div>
                <div>
                  <span>产品总规模</span>
                  <strong>
                    12.86 <small>亿元</small>
                  </strong>
                  <p>估值数据截至 08.28</p>
                </div>
                <div>
                  <span>今日已确认</span>
                  <strong>
                    9 <small>/ 12</small>
                  </strong>
                  <p>
                    <i className="dot green" />
                    75% 已完成处理
                  </p>
                </div>
                <div>
                  <span>最新数据日期</span>
                  <strong className="date-value">
                    08.28 <small>周五</small>
                  </strong>
                  <p>今天收到的数据，依然有自己的日期</p>
                </div>
              </div>
              <div className="overview-grid">
                <section className="panel chart-panel">
                  <div className="panel-header">
                    <div>
                      <h2>让长期表现，一目了然</h2>
                      <p>远山稳进一号 · A 类份额</p>
                    </div>
                    <div className="segmented" aria-label="曲线区间">
                      {['近一月', '近三月', '近六月'].map((p) => (
                        <button
                          key={p}
                          aria-pressed={period === p}
                          onClick={() => setPeriod(p)}
                          className={period === p ? 'selected' : ''}
                        >
                          {p}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="chart-summary">
                    <strong>1.1862</strong>
                    <span className="positive">
                      +18.62% <small>区间收益 · 演示</small>
                    </span>
                    <span className="chart-legend">
                      <i />
                      单位净值 <i className="muted-dot" />
                      对比产品
                    </span>
                  </div>
                  <Trend period={period} />
                  <div className="chart-caption">
                    <span>演示曲线，不作为投资或业务计算依据</span>
                    <button onClick={() => navigate('detail')}>
                      查看产品详情
                      <ArrowUpRight size={13} />
                    </button>
                  </div>
                </section>
                <section className="panel progress-panel">
                  <div className="panel-header">
                    <h2>今日处理进度</h2>
                    <span className="subtle">08.31</span>
                  </div>
                  <div className="progress-number">
                    <strong>
                      9<span>/12</span>
                    </strong>
                    <span className="status">已确认</span>
                  </div>
                  <div className="progress-blocks">
                    {Array.from({ length: 12 }, (_, i) => (
                      <i
                        key={i}
                        className={i < 9 ? 'done' : i < 11 ? 'waiting' : ''}
                      />
                    ))}
                  </div>
                  <p className="subtle progress-copy">
                    大部分数据已就绪，剩余事项有序跟进。
                  </p>
                  <div className="progress-row">
                    <span>
                      <i className="dot green" />
                      自动确认
                    </span>
                    <strong>8</strong>
                  </div>
                  <div className="progress-row">
                    <span>
                      <i className="dot clay-dot" />
                      人工处理完成
                    </span>
                    <strong>1</strong>
                  </div>
                  <div className="progress-row">
                    <span>
                      <i className="dot amber-dot" />
                      待处理
                    </span>
                    <strong>3</strong>
                  </div>
                  <Button
                    variant="outline"
                    className="full-width"
                    onClick={() => navigate('exceptions')}
                  >
                    查看待处理事项
                    <ArrowRight size={14} />
                  </Button>
                  <div className="mini-note">
                    <ShieldCheck size={14} />
                    所有处理过程均可追溯
                  </div>
                </section>
              </div>
              <section className="panel products-panel">
                <div className="panel-header">
                  <div>
                    <h2>产品快览</h2>
                    <p>最新有效数据 · 按产品与份额展示</p>
                  </div>
                  <Button variant="ghost" onClick={() => navigate('products')}>
                    全部产品
                    <ArrowRight size={14} />
                  </Button>
                </div>
                <ProductTable
                  onSelect={(index) => {
                    setProductIndex(index);
                    navigate('detail');
                  }}
                />
              </section>
              <footer className="page-footer">
                <span>
                  <ShieldCheck size={13} />
                  数据有来源，操作有记录。
                </span>
                <span>序川 / XUCHUAN · 第一阶段原型</span>
              </footer>
            </>
          ) : (
            <WorkspaceViews
              view={view}
              readOnly={readOnly}
              products={products}
              navigate={navigate}
              notify={setToast}
              Trend={Trend}
              initialProduct={productIndex}
            />
          )}
        </main>
      </div>
      {toast && (
        <div className="toast" role="status">
          <Check size={16} />
          {toast}
          <button aria-label="关闭提示" onClick={() => setToast('')}>
            <X size={14} />
          </button>
        </div>
      )}
    </div>
  );
}
export function ProductTable({
  query = '',
  onSelect,
}: {
  query?: string;
  onSelect: (index: number) => void;
}) {
  const rows = products.filter((p) =>
    (p.name + p.code).toLowerCase().includes(query.toLowerCase()),
  );
  return (
    <Table className="data-table">
      <TableHeader>
        <TableRow>
          {[
            '产品 / 份额',
            '单位净值',
            '日变动',
            '资产规模',
            '估值日期',
            '状态',
            '',
          ].map((h, i) => (
            <TableHead key={i}>{h}</TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((p) => (
          <TableRow key={p.code}>
            <TableCell>
              <button
                className="product-name"
                onClick={() => onSelect(products.indexOf(p))}
              >
                <span
                  className="product-monogram"
                  style={{ background: p.color + '19', color: p.color }}
                >
                  {p.name.slice(2, 3)}
                </span>
                <span>
                  <strong>{p.name}</strong>
                  <small>
                    {p.code} <span>·</span> {p.share}
                  </small>
                </span>
              </button>
            </TableCell>
            <TableCell className="number">{p.nav}</TableCell>
            <TableCell
              className={p.change.startsWith('+') ? 'positive' : 'negative'}
            >
              {p.change}
            </TableCell>
            <TableCell>{p.scale} 亿元</TableCell>
            <TableCell className="subtle">2026.08.28</TableCell>
            <TableCell>
              <Status>{p.status}</Status>
            </TableCell>
            <TableCell>
              <Button
                variant="ghost"
                size="icon"
                aria-label={`查看${p.name}`}
                onClick={() => onSelect(products.indexOf(p))}
              >
                <ChevronRight size={16} />
              </Button>
            </TableCell>
          </TableRow>
        ))}
        {!rows.length && (
          <TableRow>
            <TableCell colSpan={7} className="empty-result">
              没有找到匹配的产品，请调整搜索词。
            </TableCell>
          </TableRow>
        )}
      </TableBody>
    </Table>
  );
}
