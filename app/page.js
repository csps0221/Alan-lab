'use client';
import { useState } from 'react';

export default function Home() {
  const [question, setQuestion] = useState('');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    if (!question) return;
    setLoading(true);
    try {
      const res = await fetch('/api', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      });
      const data = await res.json();
      setResult(data);
    } catch (err) {
      alert('發生錯誤：' + err.message);
    }
    setLoading(false);
  };

  return (
    <div style={{ padding: '2rem', fontFamily: 'sans-serif', maxWidth: '600px', margin: '0 auto' }}>
      <h1>🔬 A.lab 全能解題實驗室</h1>
      <textarea
        rows={4}
        style={{ width: '100%', padding: '8px', marginBottom: '10px' }}
        placeholder="請在此輸入你想要發問或解答的任何問題..."
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
      />
      <button
        onClick={handleSubmit}
        disabled={loading}
        style={{ width: '100%', padding: '10px', backgroundColor: '#38BDF8', color: '#fff', border: 'none', borderRadius: '5px', cursor: 'pointer', fontWeight: 'bold' }}
      >
        {loading ? 'AI 解析中...' : '開始解題'}
      </button>

      {result && (
        <div style={{ marginTop: '20px', padding: '15px', border: '1px solid #ccc', borderRadius: '8px' }}>
          <h3>解答結果：{result.ans}</h3>
          <p>{result.reasoning}</p>
        </div>
      )}
    </div>
  );
}
