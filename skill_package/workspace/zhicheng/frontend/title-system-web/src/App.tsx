import React, { useState } from 'react';
import { Layout, Menu } from 'antd';
import {
  PieChartOutlined,
  FileAddOutlined,
  CheckCircleOutlined,
} from '@ant-design/icons';
import OverviewPage from './pages/OverviewPage';
import ApplyPage from './pages/ApplyPage';
import ApprovePage from './pages/ApprovePage';

const { Sider, Content } = Layout;

const menuItems = [
  { key: 'overview', icon: <PieChartOutlined />, label: '职称分布概览' },
  { key: 'apply', icon: <FileAddOutlined />, label: '职称申请' },
  { key: 'approve', icon: <CheckCircleOutlined />, label: '职称审批' },
];

const App: React.FC = () => {
  const [current, setCurrent] = useState('overview');
  const [collapsed, setCollapsed] = useState(false);

  const renderPage = () => {
    switch (current) {
      case 'overview': return <OverviewPage />;
      case 'apply': return <ApplyPage />;
      case 'approve': return <ApprovePage />;
      default: return <OverviewPage />;
    }
  };

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        theme="dark"
        width={220}
        style={{ background: 'linear-gradient(180deg, #001529 0%, #002140 100%)' }}
      >
        <div style={{
          height: 64,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#fff',
          fontSize: collapsed ? 16 : 18,
          fontWeight: 700,
          borderBottom: '1px solid rgba(255,255,255,0.1)',
          gap: 8,
        }}>
          🪪 {!collapsed && <span>职称管理系统</span>}
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[current]}
          items={menuItems}
          onClick={({ key }) => setCurrent(key)}
          style={{ background: 'transparent' }}
        />
      </Sider>
      <Layout>
        <Content style={{ margin: 24, minHeight: 280 }}>
          {renderPage()}
        </Content>
      </Layout>
    </Layout>
  );
};

export default App;
