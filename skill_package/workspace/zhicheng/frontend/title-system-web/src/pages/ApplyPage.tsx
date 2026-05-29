import React, { useEffect, useState, useCallback } from 'react';
import { Table, Card, Button, Input, Select, Space, Modal, Form, message, Tag } from 'antd';
import { PlusOutlined, SearchOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { fetchEmployees, fetchEmployee, fetchDepartments, createApplication, Employee } from '../api';

const titleTagColor: Record<string, string> = {
  '无职称': 'default',
  '初级职称': 'blue',
  '中级职称': 'orange',
  '高级职称': 'red',
};

const ApplyPage: React.FC = () => {
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [keyword, setKeyword] = useState('');
  const [department, setDepartment] = useState<string | undefined>(undefined);
  const [departments, setDepartments] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [empIdInput, setEmpIdInput] = useState('');
  const [empInfo, setEmpInfo] = useState<Employee | null>(null);
  const [appliedTitle, setAppliedTitle] = useState('');
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const loadEmployees = useCallback(async () => {
    setLoading(true);
    const res = await fetchEmployees({ keyword, department, page, page_size: 15 });
    setEmployees(res.data);
    setTotal(res.total);
    setLoading(false);
  }, [keyword, department, page]);

  useEffect(() => {
    loadEmployees();
  }, [loadEmployees]);

  useEffect(() => {
    fetchDepartments().then(r => setDepartments(r.data));
  }, []);

  const handleEmpInput = async (v: string) => {
    setEmpIdInput(v);
    if (v.length >= 3) {
      try {
        const emp = await fetchEmployee(v);
        setEmpInfo(emp);
      } catch {
        setEmpInfo(null);
      }
    } else {
      setEmpInfo(null);
    }
  };

  const handleSubmit = async () => {
    if (!empIdInput || !appliedTitle) {
      message.warning('请填写员工编号并选择申请职称');
      return;
    }
    setSubmitting(true);
    try {
      const res = await createApplication({ emp_id: empIdInput, applied_title: appliedTitle, reason });
      if (res.ok) {
        message.success('申请已提交成功！');
        setModalOpen(false);
        setEmpIdInput('');
        setEmpInfo(null);
        setAppliedTitle('');
        setReason('');
        loadEmployees();
      }
    } catch (e: any) {
      message.error(e.message || '提交失败');
    } finally {
      setSubmitting(false);
    }
  };

  const columns: ColumnsType<Employee> = [
    { title: '编号', dataIndex: 'emp_id', key: 'emp_id', width: 90 },
    { title: '姓名', dataIndex: 'name', key: 'name', width: 100 },
    { title: '部门', dataIndex: 'department', key: 'department', width: 140 },
    { title: '岗位', dataIndex: 'job_position', key: 'job_position', width: 130 },
    {
      title: '当前职称', dataIndex: 'professional_title', key: 'professional_title', width: 110,
      render: (v: string) => <Tag color={titleTagColor[v] || 'default'}>{v}</Tag>,
    },
    { title: '学历', dataIndex: 'education', key: 'education', width: 80 },
    { title: '工龄(年)', dataIndex: 'seniority', key: 'seniority', width: 80 },
    {
      title: '操作', key: 'action', width: 100,
      render: (_, r) => (
        <Button type="link" icon={<PlusOutlined />} onClick={() => {
          setEmpIdInput(r.emp_id);
          setEmpInfo(r);
          setAppliedTitle('');
          setReason('');
          setModalOpen(true);
        }}>
          申请职称
        </Button>
      ),
    },
  ];

  return (
    <div>
      <h2 style={{ marginBottom: 20 }}>📝 职称申请</h2>
      <Card>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16, flexWrap: 'wrap', gap: 12 }}>
          <Space>
            <Input
              placeholder="搜索员工编号或姓名"
              prefix={<SearchOutlined />}
              value={keyword}
              onChange={e => { setKeyword(e.target.value); setPage(1); }}
              style={{ width: 240 }}
              allowClear
            />
            <Select
              allowClear
              placeholder="全部部门"
              style={{ width: 160 }}
              value={department}
              onChange={v => { setDepartment(v); setPage(1); }}
              options={departments.map(d => ({ label: d, value: d }))}
            />
          </Space>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => {
            setEmpIdInput('');
            setEmpInfo(null);
            setAppliedTitle('');
            setReason('');
            setModalOpen(true);
          }}>
            提交申请
          </Button>
        </div>

        <Table
          columns={columns}
          dataSource={employees}
          rowKey="emp_id"
          loading={loading}
          pagination={{
            current: page,
            total,
            pageSize: 15,
            onChange: setPage,
            showTotal: t => `共 ${t} 人`,
          }}
          size="small"
        />
      </Card>

      <Modal
        title="📝 提交职称申请"
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={handleSubmit}
        confirmLoading={submitting}
        okText="提交申请"
      >
        <Form layout="vertical">
          <Form.Item label="员工编号" required>
            <Input
              placeholder="请输入员工编号"
              value={empIdInput}
              onChange={e => handleEmpInput(e.target.value)}
            />
          </Form.Item>
          {empInfo && (
            <div style={{ background: '#fafafa', padding: '8px 12px', borderRadius: 6, marginBottom: 12, fontSize: 13, color: '#666' }}>
              <strong>{empInfo.name}</strong> | {empInfo.department} | {empInfo.job_position}<br />
              当前职称：<Tag color={titleTagColor[empInfo.professional_title]}>{empInfo.professional_title}</Tag>
              &nbsp;学历：{empInfo.education} | 工龄：{empInfo.seniority}年
            </div>
          )}
          <Form.Item label="申请职称等级" required>
            <Select
              placeholder="请选择"
              value={appliedTitle}
              onChange={setAppliedTitle}
              options={[
                { label: '初级职称', value: '初级职称' },
                { label: '中级职称', value: '中级职称' },
                { label: '高级职称', value: '高级职称' },
              ]}
            />
          </Form.Item>
          <Form.Item label="申请理由">
            <Input.TextArea
              rows={4}
              placeholder="请输入申请理由..."
              value={reason}
              onChange={e => setReason(e.target.value)}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default ApplyPage;
