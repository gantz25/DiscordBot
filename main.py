import discord
from discord.ext import commands
import yt_dlp as youtube_dl
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import asyncio
import re
from pytube import YouTube
from keep_alive import keep_alive

# Spotify API credentials
client_id = "b993df8eb165493eb5e7dad9fc7c964f"
client_secret = "4f37d7676492403c81eeb2639e936bbd"

# Authenticate with the Spotify API
auth_manager = SpotifyClientCredentials(client_id=client_id,
                                        client_secret=client_secret)
sp = spotipy.Spotify(auth_manager=auth_manager)

# Define the intents
intents = discord.Intents.default()
intents.message_content = True  # Enable the intent to read message content

# Initialize the bot with intents
bot = commands.Bot(command_prefix="!", intents=intents)

# YouTube DL options for streaming
ytdl_format_options = {
    'format': 'bestaudio/best',
    'quiet': True,
    'extract_flat': 'in_playlist',
    'noplaylist': False,  # This allows playlist extraction
    'nocheckcertificate': True,
    'default_search': 'auto',
    'source_address':
    '0.0.0.0' , # Bind to IPv4 since IPv6 addresses cause issues sometimes
    'retries': 10,                 # Increase the number of retries
    'fragment_retries': 10,        # Retries for each fragment
    'no_warnings': True,           # Suppress warnings
    'ignoreerrors': True,          # Ignore errors
    'external_downloader': 'ffmpeg' 
}

ffmpeg_options = {'options': '-vn'}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

# Global queue to store tracks
music_queue = []
is_skipping = False


class YTDLSource(discord.PCMVolumeTransformer):

    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = ""

    @classmethod
    async def from_url(cls, url, *, loop=None):
        loop = loop or asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(
                None, lambda: ytdl.extract_info(url, download=False))
            filename = data['url']
            return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options),
                       data=data)
        except youtube_dl.utils.DownloadError as e:
            if "DRM" in str(e):
                raise ValueError(
                    "The requested content is protected by DRM and cannot be played."
                )
            else:
                raise e


def get_spotify_metadata(spotify_url):
    match = re.match(
        r"https://open.spotify.com/(playlist|track|episode|show)/([a-zA-Z0-9]+)",
        spotify_url)

    if match:
        spotify_type = match.group(1)
        spotify_id = match.group(2)
        market = 'GB'  # Replace 'GB' with the appropriate market (e.g., 'US' for the United States)

        try:
            if spotify_type == "track":
                track = sp.track(spotify_id, market=market)
                track_name = track['name']
                artists = ', '.join(
                    [artist['name'] for artist in track['artists']])
                album_name = track['album']['name']
                return [f"{track_name} {artists} {album_name}"]

            elif spotify_type == "playlist":
                tracks = []
                playlist = sp.playlist(spotify_id, market=market)
                for item in playlist['tracks']['items']:
                    track = item['track']
                    track_name = track['name']
                    artists = ', '.join(
                        [artist['name'] for artist in track['artists']])
                    album_name = track['album']['name']
                    tracks.append(f"{track_name} {artists} {album_name}")
                return tracks

            elif spotify_type == "episode":
                episode = sp.episode(spotify_id, market=market)
                episode_name = episode['name']
                show_name = episode['show']['name']
                return [f"{episode_name} {show_name}"]

            elif spotify_type == "show":
                episodes = []
                show = sp.show(spotify_id, market=market)
                show_name = show['name']
                for item in show['episodes']['items']:
                    episode_name = item['name']
                    episodes.append(f"{episode_name} {show_name}")
                return episodes
        except spotipy.exceptions.SpotifyException as e:
            print(f"Spotify API error: {e}")
            return None

    return None


async def play_next(ctx):
    global is_skipping
    if music_queue:
        url = music_queue.pop(0)
        try:
            player = await YTDLSource.from_url(url, loop=bot.loop)
            voice_client = ctx.guild.voice_client

            def after_playing(error):
                if error:
                    print(f"Error during playback: {error}")
                if not is_skipping:
                    asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop)

            is_skipping = False
            voice_client.play(player, after=after_playing)
            await ctx.send(f'**Now playing:** {player.title}')
        except ValueError as e:
            await ctx.send(str(e))
    else:
        await ctx.send("Queue is empty. No more songs to play.")


@bot.event
async def on_ready():
    print(f"We have logged in as {bot.user}")


@bot.command(name='Docome', help='Makes the bot join the voice channel')
async def come_here(ctx):
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        await channel.connect()
        await ctx.send(f"Joined {channel}!")
        await ctx.send(r"Hello master <3 /@_@/")
    else:
        await ctx.send("You need to be in a voice channel to summon the bot.")


@bot.command(name='Doleave', help='Makes the bot leave the voice channel')
async def leave(ctx):
    voice_client = ctx.guild.voice_client
    if voice_client and voice_client.is_connected():
        music_queue.clear()
        await voice_client.disconnect()
        await ctx.send("Disconnected from the voice channel.")
    else:
        await ctx.send("The bot is not connected to a voice channel.")

@bot.command(
    name='Doplay',
    help=
    'Adds a song or playlist to the queue and starts playing if not already playing'
)
async def play_stream(ctx, *, search: str):
  
        
    voice_client = ctx.guild.voice_client

    if not voice_client or not voice_client.is_connected():
        if ctx.author.voice:
            channel = ctx.author.voice.channel
            await ctx.send("coming dear master <3 /(@_@)/\n")
            voice_client = await channel.connect()
            await ctx.send(f"Joined {channel}!\nHello master <3!")
            
        else:
            await ctx.send(
                "You need to be in a voice channel to summon the bot using !come_here."
            )
            return

    if "spotify.com" in search:
        tracks = get_spotify_metadata(search)
        if not tracks:
            await ctx.send("Unable to retrieve metadata from the Spotify link."
                           )
            return

        for track in tracks:
            async with ctx.typing():
                search_result = await bot.loop.run_in_executor(
                    None, lambda: ytdl.extract_info(f"ytsearch:{track}",
                                                    download=False))
                if 'entries' in search_result and search_result['entries']:
                    youtube_url = search_result['entries'][0]['url']
                    music_queue.append(youtube_url)
                    await ctx.send(
                        f"**Added to queue:** {search_result['entries'][0]['title']},Thanl you Master <3"
                    )
                else:
                    await ctx.send(f"No results found for {track}.")
    else:
        if "playlist" in search:  # Detect if it's a YouTube playlist
            async with ctx.typing():
                search_result = await bot.loop.run_in_executor(
                    None, lambda: ytdl.extract_info(search, download=False))
                if 'entries' in search_result:
                    for entry in search_result['entries']:
                        music_queue.append(entry['url'])
                    await ctx.send(
                        f"**Added {len(search_result['entries'])} videos to the queue from the playlist. MASTER!**"
                    )
                else:
                    await ctx.send("No videos found in the playlist.")
        else:
            if not (search.startswith('http://')
                    or search.startswith('https://')):
                async with ctx.typing():
                    search_result = await bot.loop.run_in_executor(
                        None, lambda: ytdl.extract_info(f"ytsearch:{search}",
                                                        download=False))
                    if 'entries' in search_result and search_result['entries']:
                        search = search_result['entries'][0]['url']
                        await ctx.send(
                            f"**Search result:** {search_result['entries'][0]['title']}"
                        )
                    else:
                        await ctx.send("No results found.")
                        return

            music_queue.append(search)
            await ctx.send(f"Added to queue: {search}")

    if not voice_client.is_playing():
        await play_next(ctx)


@bot.command(name='Dopause', help='Pauses the currently playing song')
async def pause(ctx):
    voice_client = ctx.guild.voice_client
    if voice_client.is_playing():
        voice_client.pause()
        await ctx.send("Paused the song.")
    else:
        await ctx.send("The bot is not playing anything at the moment.")


@bot.command(name='Doresume', help='Resumes the currently paused song')
async def resume(ctx):
    voice_client = ctx.guild.voice_client
    if voice_client.is_paused():
        voice_client.resume()
        await ctx.send("Resumed the song.")
    else:
        await ctx.send("The bot is not paused.")


@bot.command(name='Dostop',
             help='Stops the currently playing song and clears the queue')
async def stop(ctx):
    voice_client = ctx.guild.voice_client
    if voice_client.is_playing():
        voice_client.stop()
        music_queue.clear()
        await ctx.send("Stopped the song and cleared the queue.")
    else:
        await ctx.send("The bot is not playing anything at the moment.")
@bot.command(name = 'Docheck', help = 'checks the songs in the queue')
async def check(ctx):
    if music_queue:
        queue_list = "\n".join([f"{i+1}. {YouTube(track).title}--{track}" for i, track in enumerate(music_queue)])
        await ctx.send(f"**Queue:**\n{queue_list}")
    else:
        await ctx.send("The queue is empty.")
@bot.command(name='Doskip', help='Skips the currently playing song')
async def skip(ctx):
            global is_skipping
            voice_client = ctx.guild.voice_client
            if voice_client.is_playing():
                is_skipping = True
                voice_client.stop()
                await ctx.send("Skipped the song.")
                await play_next(ctx)
            else:
                await ctx.send("No song is currently playing.")



if __name__ == "__main__":
    keep_alive()
    bot.run(
        "MTI3NDQ0MzkyOTEwNTg1ODY1Mg.GYRydH.Dw7QX6BqrTH0DuJu9FxXzcWYYVv-7a1svoOk5w"
    )
