import { NavLink } from 'react-router-dom'
import {
  BookmarkIcon,
  CalendarIcon,
  ChartIcon,
  HistoryIcon,
  PipelineIcon,
  SearchIcon,
  SettingsIcon,
} from '../components/icons'

const NAV_ITEMS = [
  { to: '/', label: '新建采集', Icon: SearchIcon, end: true },
  { to: '/results', label: '机会分析', Icon: ChartIcon, end: false },
  { to: '/pipeline', label: '获取闭环', Icon: PipelineIcon, end: true },
  { to: '/schedules', label: '定时任务', Icon: CalendarIcon, end: true },
  { to: '/history', label: '采集历史', Icon: HistoryIcon, end: true },
  { to: '/library', label: '机会库', Icon: BookmarkIcon, end: true },
  { to: '/settings', label: '设置', Icon: SettingsIcon, end: true },
]

export function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">◎</div>
        <div>
          <div className="brand-name">Opportunity Scout</div>
          <div className="brand-sub">商机雷达 · 本地版</div>
        </div>
      </div>

      <nav className="nav" aria-label="主导航">
        {NAV_ITEMS.map(({ to, label, Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
          >
            <Icon />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="sidebar-card">
        <strong>
          <span className="dot" />
          本地运行
        </strong>
        数据与配置只保存在本机，不上传云端。
      </div>
      <div className="sidebar-footer">v0.1 · 本地版</div>
    </aside>
  )
}
