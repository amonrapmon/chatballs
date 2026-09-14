// Волна голосового сообщения.
//
// Реальная амплитуда записи не хранится, поэтому рисунок считается из
// идентификатора сообщения: он стабилен между рендерами и одинаков в чате
// оператора и в виджете клиента — одно и то же сообщение выглядит одинаково с
// обеих сторон разговора.

export const VOICE_WAVE_BARS = 32;

export function voiceWaveHeights(seed: number, bars = VOICE_WAVE_BARS): number[] {
  const heights: number[] = [];
  let value = seed || 1;
  for (let index = 0; index < bars; index += 1) {
    value = (value * 1103515245 + 12345) % 2147483648;
    heights.push(4 + (value % 17));
  }
  return heights;
}
