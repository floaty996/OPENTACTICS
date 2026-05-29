import React, { useEffect, useState, useCallback } from 'react';
import { Table, Card, Button, Select, Space, Modal, Form, Input, message, Tag, Descriptions } from 'antd';
import { CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { fetchApplications, fetchApplication, fetchDepartments, reviewApplication, Application } from '../api';

const statusColor: Record<string, string> = {
  '待审批': 'warning',
  '已通过': 'success',
  '已驳回': 'error',
};

const titleTagColor: Record<string, string> = {
  '无职称': 'default',
  '初级职称': 'blue',
  '中级职称': 'orange',
  '高级职称': 'red',
};

const ApprovePage: React.FC = () => {
  const [apps, setApps] = useState<Application[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const [deptFilter, setDeptFilter] = useState<string | undefined>(undefined);
  const [departments, setDepartments] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);

  // 审批弹窗
  const [reviewOpen, setReviewOpen] = useState(false);
  const [currentApp, setCurrentApp] = useState<Application | null>(null);
  const [reviewer, setReviewer] = useState('管理员');
  const [reviewComment, setReviewComment] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const loadApps = useCallback(async () => {
    setLoading(true);
    const res = await fetchApplications({
      status: statusFilter,
      department: deptFilter,
      page,
      page_size: 15,
    });
    setApps(res.data);
    setTotal(res.total);
    setLoading(false);
  }, [statusFilter, deptFilter, page]);

  useEffect(() => {
    loadApps();
  }, [loadApps]);

  useEffect(() => {
    fetchDepartments().then(r => setDepartments(r.data));
  }, []);

  const openReview = async (id: number) => {
    const app = await fetchApplication(id);
    setCurrentApp(app);
    setReviewer('管理员');
    setReviewComment('');
    setReviewOpen(true);
  };

  const doReview = async (action: 'approve' | 'reject') => {
    if (!currentApp) return;
    if (!reviewer) { message.warning('请输入审批人'); return; }
    setSubmitting(true);
    try {
      const res = await reviewApplication(currentApp.id, {
        reviewer,
        review_comment: reviewComment,
        action,
      });
      if (res.ok) {
        message.success(res.message);
        setReviewOpen(false);
        loadApps();
      }
    } catch (e: any) {
      message.error(e.message || '操作失败');
    } finally {
      setSubmitting(false);
    }
  };

  const columns: ColumnsType<Application> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    {
      title: '员工', key: 'emp', width: 140,
      render: (_, r) => <><strong>{r.emp_name}</strong><br /><small style={{ color: '#999' }}>{r.emp_id}</small></>,
    },
    { title: '部门', dataIndex: 'department', key: 'department', width: 140 },
    {
      title: '当前职称', dataIndex: 'current_title', key: 'current_title', width: 100,
      render: (v: string) => <Tag color={titleTagColor[v] || 'default'}>{v}</Tag>,
    },
    {
      title: '申请职称', dataIndex: 'applied_title', key: 'applied_title', width: 100,
      render: (v: string) => <Tag color={titleTagColor[v] || 'blue'}>{v}</Tag>,
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 90,
      render: (v: string) => <Tag color={statusColor[v] || 'default'}>{v}</Tag>,
    },
    { title: '审批人', dataIndex: 'reviewer', key: 'reviewer', width: 80, render: (v?: string) => v || '—' },
    {
      title: '操作', key: 'action', width: 110,
      render: (_, r) => r.status === '待审批' ? (
        <Button type="primary" size="small" icon={<CheckCircleOutlined />} onClick={() => openReview(r.id)}>
          审批
        </Button>
      ) : (
        <small style={{ color: '#999' }}>已处理</small>
      ),
    },
  ];

  return (
    <div>
      <h2 style={{ marginBottom: 20 }}>✅ 职称审批</h2>
      <Card>
        <Space style={{ marginBottom: 16 }}>
          <Select
            allowClear
            placeholder="全部状态"
            style={{ width: 140 }}
            value={statusFilter}
            onChange={v => { setStatusFilter(v); setPage(1); }}
            options={[
              { label: '待审批', value: '待审批' },
              { label: '已通过', value: '已通过' },
              { label: '已驳回', value: '已驳回' },
            ]}
          />
          <Select
            allowClear
            placeholder="全部部门"
            style={{ width: 160 }}
            value={deptFilter}
            onChange={v => { setDeptFilter(v); setPage(1); }}
            options={departments.map(d => ({ label: d, value: d }))}
          />
        </Space>

        <Table
          columns={columns}
          dataSource={apps}
          rowKey="id"
          loading={loading}
          pagination={{
            current: page,
            total,
            pageSize: 15,
            onChange: setPage,
            showTotal: t => `共 ${t} 条`,
          }}
          size="small"
        />
      </Card>

      <Modal
        title="✅ 审批职称申请"
        open={reviewOpen}
        onCancel={() => setReviewOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setReviewOpen(false)}>取消</Button>,
          <Button key="reject" danger icon={<CloseCircleOutlined />} loading={submitting}
            onClick={() => doReview('reject')}>驳回</Button>,
          <Button key="approve" type="primary" icon={<CheckCircleOutlined />} loading={submitting}
            onClick={() => doReview('approve')}>通过</Button>,
        ]}
        width={560}
      >
        {currentApp && (
          <>
            <Descriptions column={2} size="small" bordered style={{ marginBottom: 16 }}>
              <Descriptions.Item label="员工">{currentApp.emp_name} ({currentApp.emp_id})</Descriptions.Item>
              <Descriptions.Item label="部门">{currentApp.department}</Descriptions.Item>
              <Descriptions.Item label="当前职称"><Tag>{currentApp.current_title}</Tag></Descriptions.Item>
              <Descriptions.Item label="申请职称"><Tag color="blue">{currentApp.applied_title}</Tag></Descriptions.Item>
              <Descriptions.Item label="学历">{currentApp.education}</Descriptions.Item>
              <Descriptions.Item label="工龄">{currentApp.seniority}年</Descriptions.Item>
              <Descriptions.Item label="申请理由" span={2}>{currentApp.reason || '无'}</Descriptions.Item>
            </Descriptions>
            <Form layout="vertical">
              <Form.Item label="审批人">
                <Input value={reviewer} onChange={e => setReviewer(e.target.value)} />
              </Form.Item>
              <Form.Item label="审批意见">
                <Input.TextArea rows={3} value={reviewComment} onChange={e => setReviewComment(e.target.value)} placeholder="请输入审批意见..." />
              </Form.Item>
            </Form>
          </>
        )}
      </Modal>
    </div>
  );
};

export default ApprovePage;
