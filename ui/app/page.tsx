'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { downloadPDF } from '@/lib/utils';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  pdfBase64?: string;
}

export default function CVGenerator() {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'assistant',
      content: '👋 Cześć! Wrzuć swoje CV (DOCX lub PDF) lub napisz informacje o sobie. Pomogę Ci stworzyć profesjonalne CV w PDF.',
    },
  ]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [cvFile, setCvFile] = useState<File | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const onDrop = useCallback((acceptedFiles: File[]) => {
    if (acceptedFiles.length > 0) {
      const file = acceptedFiles[0];
      if (
        file.type === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' ||
        file.type === 'application/pdf' ||
        file.name.endsWith('.docx') ||
        file.name.endsWith('.pdf')
      ) {
        setCvFile(file);
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: `✓ Plik załadowany: ${file.name} (${(file.size / 1024).toFixed(1)} KB)\n\n📝 Wpisz swoją wiadomość i kliknij "Wyślij" aby przetwarzać CV.`,
          },
        ]);
      }
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
      'application/pdf': ['.pdf'],
    },
    noClick: false,
  });

  const handleSendMessage = async () => {
    if (!inputValue.trim()) return;

    const userMessage = inputValue;
    setInputValue('');
    setMessages((prev) => [...prev, { role: 'user', content: userMessage }]);
    setIsLoading(true);

    try {
      let docx_base64: string | undefined;

      if (cvFile) {
        docx_base64 = await new Promise<string | undefined>((resolve) => {
          const reader = new FileReader();
          reader.onload = (e) => {
            try {
              const result = e.target?.result as string;
              if (!result) {
                resolve(undefined);
                return;
              }
              // Check if it's data URL format (starts with data:)
              if (result.startsWith('data:')) {
                const base64Part = result.split(',')[1];
                resolve(base64Part || undefined);
              } else {
                // If it's already base64
                resolve(result);
              }
            } catch (err) {
              console.error('Error parsing base64:', err);
              resolve(undefined);
            }
          };
          reader.onerror = (err) => {
            console.error('FileReader error:', err);
            resolve(undefined);
          };
          reader.readAsDataURL(cvFile);
        });
        
        console.log('File loaded, base64 length:', docx_base64?.length || 0);
      }

      const payload = {
        message: userMessage,
        docx_base64,
      };
      
      console.log('=== Frontend Request ===');
      console.log('Message:', userMessage);
      console.log('Has docx_base64:', !!docx_base64);
      console.log('Base64 length:', docx_base64?.length || 0);
      console.log('Payload size:', JSON.stringify(payload).length, 'bytes');

      const response = await fetch('/api/process-cv', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      console.log('Response status:', response.status, response.statusText);
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error('Response error:', errorText);
        throw new Error(`Server error: ${response.status} - ${errorText.substring(0, 200)}`);
      }

      const result = await response.json();
      console.log('Result:', { success: result.success, hasResponse: !!result.response, hasPDF: !!result.pdf_base64 });

      if (result.success) {
        const assistantMsg: Message = {
          role: 'assistant',
          content: result.response || 'Processing completed',
        };

        if (result.pdf_base64) {
          assistantMsg.pdfBase64 = result.pdf_base64;
        }

        setMessages((prev) => [...prev, assistantMsg]);

        if (result.pdf_base64) {
          downloadPDF(result.pdf_base64, `CV_${Date.now()}.pdf`);
        }
      } else {
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: `❌ Error: ${result.error}`,
          },
        ]);
      }
    } catch (error) {
      console.error('=== Frontend Error ===', error);
      const errorMessage = error instanceof Error ? error.message : String(error);
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: `❌ Error: ${errorMessage}\n\n💡 Check browser console (F12) for details`,
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  return (
    <div className="flex h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
      {/* Sidebar - File Upload */}
      <div className="w-72 bg-white border-r border-gray-200 p-6 flex flex-col">
        <h2 className="text-lg font-bold text-gray-900 mb-4">CV Generator</h2>

        <div
          {...getRootProps()}
          className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition flex-1 flex items-center justify-center ${
            isDragActive
              ? 'border-indigo-500 bg-indigo-50'
              : cvFile
                ? 'border-green-300 bg-green-50'
                : 'border-gray-300 hover:border-indigo-400'
          }`}
        >
          <input {...getInputProps()} />
          {cvFile ? (
            <div className="space-y-2">
              <div className="text-2xl">✓</div>
              <p className="text-sm font-semibold text-gray-900">{cvFile.name}</p>
              <p className="text-xs text-gray-500">{(cvFile.size / 1024).toFixed(1)} KB</p>
            </div>
          ) : (
            <div className="space-y-2">
              <div className="text-3xl">📁</div>
              <p className="text-sm font-semibold text-gray-900">
                {isDragActive ? 'Drop here' : 'Upload CV'}
              </p>
              <p className="text-xs text-gray-500">DOCX or PDF</p>
            </div>
          )}
        </div>

        <div className="mt-4 pt-4 border-t border-gray-200 text-xs text-gray-600">
          <p className="font-semibold mb-2">Instructions:</p>
          <ul className="space-y-1">
            <li>1. Upload your CV file</li>
            <li>2. Describe your needs</li>
            <li>3. AI will generate PDF</li>
          </ul>
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col">
        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {messages.map((msg, idx) => (
            <div
              key={idx}
              className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-2xl rounded-lg p-4 ${
                  msg.role === 'user'
                    ? 'bg-indigo-600 text-white'
                    : 'bg-white text-gray-900 border border-gray-200'
                }`}
              >
                <p className="whitespace-pre-wrap">{msg.content}</p>
                {msg.pdfBase64 && (
                  <button
                    onClick={() => downloadPDF(msg.pdfBase64!, `CV_${idx}.pdf`)}
                    className="mt-2 text-sm bg-indigo-100 text-indigo-700 px-3 py-1 rounded hover:bg-indigo-200"
                  >
                    📥 Download PDF
                  </button>
                )}
              </div>
            </div>
          ))}
          {isLoading && (
            <div className="flex justify-start">
              <div className="bg-white text-gray-900 border border-gray-200 rounded-lg p-4">
                <div className="flex items-center gap-2">
                  <span className="animate-spin">⚙️</span>
                  <span>Processing...</span>
                </div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input Area */}
        <div className="border-t border-gray-200 bg-white p-4 space-y-3">
          <textarea
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyPress={handleKeyPress}
            disabled={isLoading}
            placeholder="Type your message... (Shift+Enter for new line)"
            className="w-full p-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none disabled:bg-gray-100"
            rows={3}
          />

          <button
            onClick={handleSendMessage}
            disabled={isLoading || !inputValue.trim()}
            className={`w-full py-3 rounded-lg font-semibold transition ${
              isLoading || !inputValue.trim()
                ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                : 'bg-indigo-600 text-white hover:bg-indigo-700 active:scale-95'
            }`}
          >
            {isLoading ? '⏳ Processing...' : '📤 Send'}
          </button>
        </div>
      </div>
    </div>
  );
}
