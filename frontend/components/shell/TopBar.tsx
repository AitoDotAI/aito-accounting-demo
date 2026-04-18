interface TopBarProps {
  breadcrumb: string;
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
  live?: boolean;
}

export default function TopBar({ breadcrumb, title, subtitle, actions, live }: TopBarProps) {
  return (
    <div className="topbar">
      <div>
        <div className="topbar-breadcrumb">{breadcrumb}</div>
        <div className="topbar-title">{title}</div>
      </div>
      {subtitle && (
        <>
          <div className="topbar-sep" />
          <div className="topbar-sub">{subtitle}</div>
        </>
      )}
      <div className="topbar-right">
        {live && <span className="live-dot">Live</span>}
        {actions}
      </div>
    </div>
  );
}
