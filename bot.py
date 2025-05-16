import discord
from discord.ext import commands
import yt_dlp
import whisper
import asyncio
import os
import pyaudio
import wave
import uuid
import torch
from discord import FFmpegPCMAudio

# Настройка бота
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Настройка YTDL
ytdl_format_options = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'extract_flat': False,
    'quiet': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
}
ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)
whisper_model = whisper.load_model("medium")

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        if 'entries' in data:
            data = data['entries'][0]
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

def record_audio():
    # Генерация уникального имени для временного файла
    filename = f"temp_{uuid.uuid4().hex}.wav"

    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000
    CHUNK = 1024
    RECORD_SECONDS = 5

    audio = pyaudio.PyAudio()
    stream = audio.open(format=FORMAT, channels=CHANNELS,
                        rate=RATE, input=True,
                        frames_per_buffer=CHUNK)

    print("Запись начата...")

    frames = []
    for _ in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
        data = stream.read(CHUNK)
        frames.append(data)

    print("Запись завершена.")

    stream.stop_stream()
    stream.close()
    audio.terminate()

    with wave.open(filename, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(audio.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))

    return filename


async def process_audio(ctx):
    loop = asyncio.get_running_loop()
    audio_file = await loop.run_in_executor(None, record_audio)

    try:
        result = await loop.run_in_executor(None, lambda: whisper_model.transcribe(audio_file))
        text = result['text'].lower().strip()
        print(f"Распознано: {text}")

        if text:
            await handle_voice_command(ctx, text)
        else:
            await ctx.send("Не удалось распознать речь.")
    except Exception as e:
        await ctx.send(f"Ошибка при распознавании: {e}")
    finally:
        if os.path.exists(audio_file):
            os.remove(audio_file)
async def handle_voice_command(ctx, text):
    if any(cmd in text for cmd in ["play", "включи", "проиграй"]):
        song_name = text
        for word in ["play", "включи", "проиграй"]:
            song_name = song_name.replace(word, "")
        song_name = song_name.strip()
        await play_song(ctx, song_name)
    elif any(cmd in text for cmd in ["pause", "пауза", "останови"]):
        await pause_song(ctx)
    elif any(cmd in text for cmd in ["resume", "продолжи", "продолжить"]):
        await resume_song(ctx)
    elif any(cmd in text for cmd in ["stop", "стоп", "остановить"]):
        await stop_song(ctx)
    else:
        await ctx.send("Команда не распознана. Попробуй: play/включи, pause/пауза, resume/продолжи, stop/стоп.")

async def play_song(ctx, song_name):
    search_url = f"ytsearch1:{song_name}"

    if ctx.voice_client:
        vc = ctx.voice_client
        if vc.is_playing():
            vc.stop()
    else:
        if ctx.author.voice:
            vc = await ctx.author.voice.channel.connect()
        else:
            await ctx.send('Ты не в голосовом канале!')
            return

    try:
        player = await YTDLSource.from_url(search_url, loop=bot.loop, stream=True)
        vc.play(player, after=lambda e: print(f"Ошибка воспроизведения: {e}") if e else None)
        await ctx.send(f'🎶 Сейчас играет: {player.title}')
    except Exception as e:
        await ctx.send(f"Не удалось воспроизвести: {e}")

async def pause_song(ctx):
    vc = ctx.voice_client
    if vc and vc.is_playing():
        vc.pause()
        await ctx.send("Музыка на паузе.")
    else:
        await ctx.send("Сейчас ничего не играет.")

async def resume_song(ctx):
    vc = ctx.voice_client
    if vc and vc.is_paused():
        vc.resume()
        await ctx.send("Продолжаю воспроизведение.")
    else:
        await ctx.send("Музыка не на паузе.")

async def stop_song(ctx):
    vc = ctx.voice_client
    if vc and vc.is_playing():
        vc.stop()
        await ctx.send("Музыка остановлена.")
    else:
        await ctx.send("Сейчас ничего не играет.")

@bot.command(name="listen", help="Слушать голосовую команду")
async def listen(ctx):
    await ctx.send("Я слушаю. Скажи команду.")
    await process_audio(ctx)

@bot.command(name="join", help="Подключить бота к голосовому каналу")
async def join(ctx):
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        if ctx.voice_client:
            await ctx.voice_client.disconnect()
        await channel.connect()
        await ctx.send(f"Подключён к {channel.name}")
    else:
        await ctx.send("Ты не в голосовом канале!")

@bot.command(name="leave", help="Отключить бота от голосового канала")
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Отключился.")
    else:
        await ctx.send("Я не в голосовом канале.")

# Запуск бота
if __name__ == "__main__":
    bot.run('MTM3MTYyMDkwOTE2MDMzMzQ1Mw.GnZ8Vv.xICIAAaYCLkE0jFrgmfAkSW0yoPG_O_hwgvyH4')  # Замените на НОВЫЙ безопасный токен
