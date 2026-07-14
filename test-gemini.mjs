import { GoogleGenAI } from '@google/genai';
import dotenv from 'dotenv';
dotenv.config();

async function testGemini() {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    console.error('GEMINI_API_KEY is not set in the environment.');
    process.exit(1);
  }
  
  try {
    const ai = new GoogleGenAI({ apiKey });
    console.log('Sending test request to Gemini...');
    const res = await ai.models.generateContent({
      model: 'gemini-2.5-flash',
      contents: 'Respond with OK if you receive this.'
    });
    console.log('Gemini responded:', res.text);
    console.log('Gemini API key is configured correctly and working.');
  } catch (err) {
    console.error('Gemini API test failed:', err);
  }
}
testGemini();
