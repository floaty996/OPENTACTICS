import React, { useEffect, useState } from 'react';
import { Card, Row, Col, Statistic, Select, Spin, Table, Tag } from 'antd';
import ReactEChartsCore from 'echarts-for-react';
import {
  fetchOverview,
  fetchTitleDistribution,
  fetchTitleByEducation,
  fetchDepartments,
  fetchEmployees,
  fetchEmployeesByTitle,
  OverviewData,
  DeptDistRow,
  EduDistRow,
  Employee,
} from '../api';

const titleColor = (title: string) => {
  const map: Record<string, string> = {
    '无职称': '#d9d9d9',
    '初级职称': '#2f54eb',
    '中级职称': '#d46b08',
    '高级职称': '#cf1322',
  };
  return map[title] || '#1890ff';
};

const titleColorMap: Record<string, string> = {
  '无职称': 'default',
  '初级职称': 'blue',
  '中级职称': 'orange',
  '高级职称': 'red',
};

const OverviewPage: React.FC = () => {
  const [overview, setOverview] = useState<OverviewData | null>(null);
  const [departments, setDepartments] = useState<string[]>([]);
  const [deptFilter, setDeptFilter] = useState<string | undefined>(undefined);
  const [titleFilter, setTitleFilter] = useState<string | undefined>(undefined);
  const [deptDist, setDeptDist] = useState<DeptDistRow[]>([]);
  const [eduDist, setEduDist] = useState<EduDistRow[]>([]);
  const [loading, setLoading] = useState(true);

  // 按职称筛选的员工列表
  const [titleEmployees, setTitleEmployees] = useState<Employee[]>([]);
  const [titleEmpTotal, setTitleEmpTotal] = useState(0);
  const [titleEmpPage, setTitleEmpPage] = useState(1);
  const [titleEmpLoading, setTitleEmpLoading] = useState(false);

  useEffect(() => {
    Promise.all([fetchOverview(), fetchDepartments()]).then(([ov, dept]) => {
      setOverview(ov);
      setDepartments(dept.data);
      setLoading(false);
    });
  }, []);

  useEffect(() => {
    fetchTitleDistribution(deptFilter).then(r => setDeptDist(r.data));
    fetchTitleByEducation().then(r => setEduDist(r.data));
  }, [deptFilter]);

  // 按职称筛选员工
  useEffect(() => {
    if (titleFilter) {
      setTitleEmpLoading(true);
      fetchEmployeesByTitle({ professional_title: titleFilter, department: deptFilter, page: titleEmpPage, page_size: 15 })
        .then(r => { setTitleEmployees(r.data); setTitleEmpTotal(r.total); })
        .finally(() => setTitleEmpLoading(false));
    } else {
      setTitleEmployees([]);
      setTitleEmpTotal(0);
    }
  }, [titleFilter, deptFilter, titleEmpPage]);

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '80px auto' }} />;

  const deptChartOption = {
    tooltip: { trigger: 'axis' as const },
    legend: { data: ['无职称', '初级职称', '中级职称', '高级职称'] },
    xAxis: { type: 'category' as const, data: deptDist.map(d => d.department), axisLabel: { rotate: 30 } },
    yAxis: { type: 'value' as const },
    series: [
      { name: '无职称', type: 'bar' as const, stack: 'total', data: deptDist.map(d => d.no_title), itemStyle: { color: '#d9d9d9' } },
      { name: '初级职称', type: 'bar' as const, stack: 'total', data: deptDist.map(d => d.junior), itemStyle: { color: '#2f54eb' } },
      { name: '中级职称', type: 'bar' as const, stack: 'total', data: deptDist.map(d => d.mid), itemStyle: { color: '#d46b08' } },
      { name: '高级职称', type: 'bar' as const, stack: 'total', data: deptDist.map(d => d.senior), itemStyle: { color: '#cf1322' } },
    ],
  };

  const eduChartOption = {
    tooltip: { trigger: 'axis' as const },
    legend: { data: ['无职称', '初级职称', '中级职称', '高级职称'] },
    xAxis: { type: 'category' as const, data: eduDist.map(d => d.education) },
    yAxis: { type: 'value' as const },
    series: [
      { name: '无职称', type: 'bar' as const, stack: 'total', data: eduDist.map(d => d.no_title), itemStyle: { color: '#d9d9d9' } },
      { name: '初级职称', type: 'bar' as const, stack: 'total', data: eduDist.map(d => d.junior), itemStyle: { color: '#2f54eb' } },
      { name: '中级职称', type: 'bar' as const, stack: 'total', data: eduDist.map(d => d.mid), itemStyle: { color: '#d46b08' } },
      { name: '高级职称', type: 'bar' as const, stack: 'total', data: eduDist.map(d => d.senior), itemStyle: { color: '#cf1322' } },
    ],
  };

  return (
    <div>
      <h2 style={{ marginBottom: 20 }}>📊 职称分布概览</h2>
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}><Card><Statistic title="员工总数" value={overview?.employee_count} valueStyle={{ color: '#1890ff' }} /></Card></Col>
        <Col span={6}><Card><Statistic title="部门数" value={overview?.department_count} valueStyle={{ color: '#52c41a' }} /></Card></Col>
        <Col span={6}><Card><Statistic title="申请总数" value={overview?.application_count} valueStyle={{ color: '#fa8c16' }} /></Card></Col>
        <Col span={6}><Card><Statistic title="待审批" value={overview?.application_status?.['待审批'] || 0} valueStyle={{ color: '#ff4d4f' }} /></Card></Col>
      </Row>

      <Card style={{ marginBottom: 16 }} size="small" title={<><span role="img" aria-label="filter">🔍</span> 筛选条件</>}>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <Select
            allowClear
            placeholder="全部部门"
            style={{ width: 200 }}
            value={deptFilter}
            onChange={v => { setDeptFilter(v); setTitleEmpPage(1); }}
            options={departments.map(d => ({ label: d, value: d }))}
          />
          <Select
            allowClear
            placeholder="全部职称"
            style={{ width: 200 }}
            value={titleFilter}
            onChange={v => { setTitleFilter(v); setTitleEmpPage(1); }}
            options={[
              { label: '无职称', value: '无职称' },
              { label: '初级职称', value: '初级职称' },
              { label: '中级职称', value: '中级职称' },
              { label: '高级职称', value: '高级职称' },
            ]}
          />
        </div>
      </Card>

      <Row gutter={16}>
        <Col span={12}>
          <Card title={<><span role="img" aria-label="bar">📊</span> 各部门职称分布</>}>
            <ReactEChartsCore option={deptChartOption} style={{ height: 340 }} />
          </Card>
        </Col>
        <Col span={12}>
          <Card title={<><span role="img" aria-label="edu">🎓</span> 学历 vs 职称分布</>}>
            <ReactEChartsCore option={eduChartOption} style={{ height: 340 }} />
          </Card>
        </Col>
      </Row>

      {/* 按职称筛选的人员信息表 */}
      <Card style={{ marginTop: 16 }} title={<><span role="img" aria-label="users">👥</span> 人员信息{titleFilter ? <span style={{ fontSize: 14, color: '#999', fontWeight: 400, marginLeft: 8 }}>— 当前筛选: 「{titleFilter}」</span> : ''}</>}>
        <Table<Employee>
          rowKey="emp_id"
          dataSource={titleEmployees}
          loading={titleEmpLoading}
          pagination={{
            current: titleEmpPage,
            pageSize: 15,
            total: titleEmpTotal,
            onChange: (p) => setTitleEmpPage(p),
            showTotal: (t) => `共 ${t} 人`,
          }}
          columns={[
            { title: '编号', dataIndex: 'emp_id', key: 'emp_id', render: (v) => <strong>{v}</strong> },
            { title: '姓名', dataIndex: 'name', key: 'name' },
            { title: '部门', dataIndex: 'department', key: 'department' },
            { title: '岗位', dataIndex: 'job_position', key: 'job_position' },
            { title: '学历', dataIndex: 'education', key: 'education' },
            {
              title: '职称',
              dataIndex: 'professional_title',
              key: 'professional_title',
              render: (v: string) => <Tag color={titleColorMap[v] || 'default'}>{v}</Tag>,
            },
            { title: '工龄', dataIndex: 'seniority', key: 'seniority', render: (v: number) => `${v}年` },
          ]}
          locale={{ emptyText: titleFilter ? '暂无符合条件的人员' : '请选择职称进行筛选' }}
        />
      </Card>
    </div>
  );
};

export default OverviewPage;
