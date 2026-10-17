# ╔══════════════════════════════════════════════════════╗
#  노래 자판기 봇 — py-cord + 진짜 컴포넌트 v2
#  pip install py-cord>=2.7.0 yt-dlp PyNaCl
# ╚══════════════════════════════════════════════════════╝
import discord
from discord import option
from discord.ext import commands
import asyncio
import yt_dlp
import os

TOKEN = os.environ.get("TOKEN")  # Railway 환경변수에서 토큰 가져오기

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(intents=intents)

# ══════════════════════════════════════════════════════
#  yt-dlp 설정
# ══════════════════════════════════════════════════════
YTDL_OPTS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "source_address": "0.0.0.0",
}
FFMPEG_OPTS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}
ytdl = yt_dlp.YoutubeDL(YTDL_OPTS)


async def search_youtube(query: str, count: int = 5) -> list[dict]:
    loop = asyncio.get_event_loop()
    try:
        data = await loop.run_in_executor(
            None, lambda: ytdl.extract_info(f"ytsearch{count}:{query}", download=False)
        )
        return data.get("entries", []) or []
    except Exception as e:
        print(f"[search 오류] {e}")
        return []


async def extract_stream_url(url: str) -> dict | None:
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(
            None, lambda: ytdl.extract_info(url, download=False)
        )
    except Exception as e:
        print(f"[extract 오류] {e}")
        return None


def get_best_stream(info: dict) -> str | None:
    for fmt in (info.get("formats") or []):
        if fmt.get("acodec") != "none" and fmt.get("vcodec") == "none":
            return fmt["url"]
    return info.get("url")


def get_small_thumb(info: dict) -> str | None:
    thumbs = [t for t in (info.get("thumbnails") or []) if t.get("url")]
    if thumbs:
        return min(thumbs, key=lambda t: (t.get("width") or 9999) * (t.get("height") or 9999))["url"]
    return info.get("thumbnail")


def fmt_dur(seconds) -> str:
    s = int(seconds or 0)
    return f"{s // 60}:{s % 60:02d}"


# ══════════════════════════════════════════════════════
#  서버별 상태
# ══════════════════════════════════════════════════════
guild_states: dict[int, dict] = {}


def get_state(guild_id: int) -> dict:
    if guild_id not in guild_states:
        guild_states[guild_id] = {
            "queue": [],
            "current": None,
            "paused": False,
            "volume": 1.0,
            "panel_msg": None,
        }
    return guild_states[guild_id]


# ══════════════════════════════════════════════════════
#  재생 엔진
# ══════════════════════════════════════════════════════
async def play_next(guild: discord.Guild):
    state = get_state(guild.id)
    vc = guild.voice_client

    if not vc or not state["queue"]:
        state["current"] = None
        await refresh_panel(guild.id)
        return

    info = state["queue"].pop(0)
    state["current"] = info
    state["paused"] = False

    source = discord.FFmpegPCMAudio(info["url"], **FFMPEG_OPTS)
    source = discord.PCMVolumeTransformer(source, volume=state["volume"])

    def after_cb(err):
        if err:
            print(f"[재생 오류] {err}")
        asyncio.run_coroutine_threadsafe(play_next(guild), bot.loop)

    vc.play(source, after=after_cb)
    await refresh_panel(guild.id)


async def refresh_panel(guild_id: int):
    state = get_state(guild_id)
    if not state["panel_msg"]:
        return
    try:
        view = build_panel_view(guild_id)
        # 컴포넌트 v2: components 파라미터로 업데이트
        await state["panel_msg"].edit(view=view)
    except Exception as e:
        print(f"[패널 갱신 오류] {e}")


# ══════════════════════════════════════════════════════
#  컴포넌트 v2 — 컨트롤 패널 빌더
# ══════════════════════════════════════════════════════
def build_panel_view(guild_id: int) -> discord.ui.View:
    """
    컴포넌트 v2: embed 없이 Container > Section/TextDisplay/Button 으로만 구성
    """
    state = get_state(guild_id)
    cur = state["current"]
    paused = state["paused"]
    queue = state["queue"]

    # ── 컨테이너 (컴포넌트 v2 최상위) ──────────────────
    container = discord.ui.Container(accent_colour=discord.Colour.blurple())

    if cur:
        thumb_url = get_small_thumb(cur)
        dur_str = fmt_dur(cur.get("duration"))
        vol_str = f"{round(state['volume'] * 100)}%"
        queue_str = f"{len(queue)}곡"
        title = cur["title"]
        page_url = cur.get("webpage_url") or ""

        # 썸네일 + 곡 정보 섹션
        section = discord.ui.Section(
            discord.ui.TextDisplay(
                f"### 🎵 지금 재생 중\n"
                f"**[{title}]({page_url})**\n\n"
                f"⏱ `{dur_str}`　📋 대기열 `{queue_str}`　🔊 볼륨 `{vol_str}`"
            ),
            accessory=(
                discord.ui.Thumbnail(url=thumb_url)
                if thumb_url else None
            ),
        )
        container.add_item(section)
    else:
        container.add_item(discord.ui.TextDisplay(
            "### 🎰 노래 자판기\n"
            "재생 중인 곡이 없어요.\n"
            "`/노래자판기` 로 노래를 골라보세요!"
        ))

    # 구분선
    container.add_item(discord.ui.Separator())

    # 재생 컨트롤 버튼 행
    pause_label = "▶ 재개" if paused else "⏸ 일시정지"
    pause_style = discord.ButtonStyle.success if paused else discord.ButtonStyle.primary

    action_row = discord.ui.ActionRow(
        discord.ui.Button(
            label=pause_label,
            style=pause_style,
            custom_id=f"cp:pause:{guild_id}",
        ),
        discord.ui.Button(
            label="⏭ 스킵",
            style=discord.ButtonStyle.secondary,
            custom_id=f"cp:skip:{guild_id}",
        ),
        discord.ui.Button(
            label="⏹ 정지",
            style=discord.ButtonStyle.danger,
            custom_id=f"cp:stop:{guild_id}",
        ),
    )
    container.add_item(action_row)

    # 볼륨 + 자판기 버튼 행
    vol_row = discord.ui.ActionRow(
        discord.ui.Button(
            label="🔉 -10%",
            style=discord.ButtonStyle.secondary,
            custom_id=f"cp:vol_dn:{guild_id}",
        ),
        discord.ui.Button(
            label="🔊 +10%",
            style=discord.ButtonStyle.secondary,
            custom_id=f"cp:vol_up:{guild_id}",
        ),
        discord.ui.Button(
            label="🎰 자판기 열기",
            style=discord.ButtonStyle.secondary,
            custom_id=f"cp:vending:{guild_id}",
        ),
    )
    container.add_item(vol_row)

    # View에 컨테이너 담기 (is_components_v2=True 플래그)
    view = discord.ui.View(timeout=None)
    view.add_item(container)
    return view


# ══════════════════════════════════════════════════════
#  컨트롤 패널 버튼 인터랙션 처리
# ══════════════════════════════════════════════════════
@bot.listen("on_interaction")
async def on_panel_interaction(interaction: discord.Interaction):
    if interaction.type != discord.InteractionType.component:
        return
    cid: str = interaction.data.get("custom_id", "")
    if not cid.startswith("cp:"):
        return

    parts = cid.split(":")
    action = parts[1]
    guild_id = interaction.guild_id
    state = get_state(guild_id)
    vc = interaction.guild.voice_client

    if action == "pause":
        if not vc:
            return await interaction.response.send_message("봇이 통화방에 없어요!", ephemeral=True)
        if vc.is_playing():
            vc.pause(); state["paused"] = True
        elif vc.is_paused():
            vc.resume(); state["paused"] = False
        view = build_panel_view(guild_id)
        await interaction.response.edit_message(view=view)

    elif action == "skip":
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
        await interaction.response.defer()

    elif action == "stop":
        state["queue"].clear()
        state["current"] = None
        state["paused"] = False
        if vc:
            vc.stop()
            await vc.disconnect()
        view = build_panel_view(guild_id)
        await interaction.response.edit_message(view=view)

    elif action == "vol_dn":
        state["volume"] = max(0.0, round(state["volume"] - 0.1, 1))
        if vc and vc.source:
            vc.source.volume = state["volume"]
        view = build_panel_view(guild_id)
        await interaction.response.edit_message(view=view)

    elif action == "vol_up":
        state["volume"] = min(2.0, round(state["volume"] + 0.1, 1))
        if vc and vc.source:
            vc.source.volume = state["volume"]
        view = build_panel_view(guild_id)
        await interaction.response.edit_message(view=view)

    elif action == "vending":
        await interaction.response.defer(ephemeral=True)
        await show_vending_machine(interaction)


# ══════════════════════════════════════════════════════
#  컴포넌트 v2 — 자판기 Step 1: 통화방 선택
# ══════════════════════════════════════════════════════
async def show_vending_machine(interaction: discord.Interaction):
    guild = interaction.guild
    voice_channels = [
        ch for ch in guild.channels
        if isinstance(ch, discord.VoiceChannel)
        and ch.permissions_for(guild.me).connect
    ]

    if not voice_channels:
        return await interaction.followup.send("❌ 입장 가능한 통화방이 없어요!", ephemeral=True)

    # 컴포넌트 v2 자판기 UI
    container = discord.ui.Container(accent_colour=discord.Colour.blurple())
    container.add_item(discord.ui.TextDisplay(
        "## 🎰 노래 자판기\n"
        "**Step 1** — 봇이 들어갈 통화방을 선택하세요\n"
        "선택하면 노래 검색창이 자동으로 열려요!"
    ))
    container.add_item(discord.ui.Separator())

    # 통화방 Select Menu
    options = [
        discord.SelectOption(
            label=ch.name,
            value=str(ch.id),
            description=f"인원: {len(ch.members)}명",
            emoji="🔊",
        )
        for ch in voice_channels[:25]
    ]
    select_row = discord.ui.ActionRow(
        discord.ui.Select(
            placeholder="🔊 통화방을 선택하세요...",
            options=options,
            custom_id="vending:vc_select",
        )
    )
    container.add_item(select_row)

    view = discord.ui.View(timeout=60)
    view.add_item(container)

    if interaction.response.is_done():
        await interaction.followup.send(view=view, ephemeral=True,
                                        flags=discord.MessageFlags(is_components_v2=True))
    else:
        await interaction.response.send_message(view=view, ephemeral=True,
                                                 flags=discord.MessageFlags(is_components_v2=True))


# ══════════════════════════════════════════════════════
#  자판기 Select 인터랙션 처리
# ══════════════════════════════════════════════════════
@bot.listen("on_interaction")
async def on_vending_interaction(interaction: discord.Interaction):
    if interaction.type != discord.InteractionType.component:
        return
    cid: str = interaction.data.get("custom_id", "")

    # 통화방 선택
    if cid == "vending:vc_select":
        channel_id = int(interaction.data["values"][0])
        channel = interaction.guild.get_channel(channel_id)
        if not channel:
            return await interaction.response.send_message("❌ 통화방을 찾을 수 없어요.", ephemeral=True)

        vc = interaction.guild.voice_client
        try:
            if vc is None:
                await channel.connect()
            elif vc.channel.id != channel_id:
                await vc.move_to(channel)
        except Exception as e:
            return await interaction.response.send_message(f"❌ 입장 실패: {e}", ephemeral=True)

        # 검색 모달 열기
        await interaction.response.send_modal(SearchModal(channel_id))

    # 다시 검색
    elif cid == "vending:research":
        vc = interaction.guild.voice_client
        vc_id = vc.channel.id if vc else 0
        await interaction.response.send_modal(SearchModal(vc_id))

    # 검색 결과 선택 버튼
    elif cid.startswith("vending:pick:"):
        await handle_pick(interaction, cid)


async def handle_pick(interaction: discord.Interaction, cid: str):
    """검색 결과 버튼 클릭 → 재생"""
    await interaction.response.defer(ephemeral=True, thinking=True)

    # custom_id = "vending:pick:{guild_id}:{index}"
    parts = cid.split(":")
    index = int(parts[3])
    guild_id = interaction.guild_id

    # 캐시에서 검색 결과 꺼내기
    cached = _search_cache.get(guild_id)
    if not cached or index >= len(cached):
        return await interaction.followup.send("❌ 검색 결과가 만료됐어요. 다시 검색해주세요.", ephemeral=True)

    item = cached[index]
    webpage_url = item.get("webpage_url") or item.get("url")
    info = await extract_stream_url(webpage_url)
    if not info:
        return await interaction.followup.send("❌ 재생 URL 추출 실패.", ephemeral=True)

    info["url"] = get_best_stream(info)

    state = get_state(guild_id)
    state["queue"].append(info)

    vc = interaction.guild.voice_client
    if vc and not vc.is_playing() and not vc.is_paused():
        await play_next(interaction.guild)

    view = build_panel_view(guild_id)

    if state["panel_msg"]:
        try:
            await state["panel_msg"].edit(view=view)
        except Exception:
            pass
        await interaction.followup.send(
            f"✅ **{info['title']}** 을(를) 대기열에 추가했어요!", ephemeral=True
        )
    else:
        msg = await interaction.followup.send(
            view=view,
            flags=discord.MessageFlags(is_components_v2=True)
        )
        state["panel_msg"] = msg


# ══════════════════════════════════════════════════════
#  검색 결과 임시 캐시 (guild_id → list[dict])
# ══════════════════════════════════════════════════════
_search_cache: dict[int, list[dict]] = {}


# ══════════════════════════════════════════════════════
#  컴포넌트 v2 — 검색 모달
# ══════════════════════════════════════════════════════
class SearchModal(discord.ui.Modal):
    def __init__(self, voice_channel_id: int):
        super().__init__(title="🔍 노래 검색")
        self.voice_channel_id = voice_channel_id
        self.add_item(discord.ui.InputText(
            label="검색어",
            placeholder="예: 아이유 밤편지, BTS Dynamite, 뉴진스 Hype Boy ...",
            min_length=1,
            max_length=100,
            style=discord.InputTextStyle.short,
        ))

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        query = self.children[0].value
        results = await search_youtube(query, count=5)

        if not results:
            return await interaction.followup.send(
                "❌ 검색 결과가 없어요. 다른 검색어를 시도해보세요!", ephemeral=True
            )

        guild_id = interaction.guild_id
        _search_cache[guild_id] = results

        # ── 컴포넌트 v2 검색 결과 UI ──────────────────
        container = discord.ui.Container(accent_colour=discord.Colour.blurple())
        container.add_item(discord.ui.TextDisplay(
            f"## 🎰 노래 자판기 — 검색 결과\n"
            f"**\"{query}\"** 검색 결과예요. 원하는 곡을 골라주세요!"
        ))
        container.add_item(discord.ui.Separator())

        # 결과 5개를 Section으로 표시 (썸네일 + 정보 + 버튼)
        rank_emoji = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
        for i, item in enumerate(results[:5]):
            dur_str = fmt_dur(item.get("duration"))
            uploader = item.get("uploader") or item.get("channel") or "알 수 없음"
            title = item["title"]
            thumb = get_small_thumb(item)

            section = discord.ui.Section(
                discord.ui.TextDisplay(
                    f"**{rank_emoji[i]} {title[:60]}{'...' if len(title) > 60 else ''}**\n"
                    f"👤 {uploader}　⏱ {dur_str}"
                ),
                accessory=discord.ui.Button(
                    label="선택",
                    style=discord.ButtonStyle.primary if i == 0 else discord.ButtonStyle.secondary,
                    custom_id=f"vending:pick:{guild_id}:{i}",
                ),
            )
            container.add_item(section)
            if i < 4:
                container.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))

        container.add_item(discord.ui.Separator())

        # 다시 검색 버튼
        rerow = discord.ui.ActionRow(
            discord.ui.Button(
                label="🔍 다시 검색",
                style=discord.ButtonStyle.secondary,
                custom_id="vending:research",
            )
        )
        container.add_item(rerow)

        view = discord.ui.View(timeout=120)
        view.add_item(container)

        await interaction.followup.send(
            view=view,
            ephemeral=True,
            flags=discord.MessageFlags(is_components_v2=True),
        )


# ══════════════════════════════════════════════════════
#  슬래시 커맨드
# ══════════════════════════════════════════════════════
@bot.slash_command(name="노래자판기", description="🎰 노래 자판기 — 통화방 선택 → 검색 → 재생!")
async def vending_machine(ctx: discord.ApplicationContext):
    await show_vending_machine(ctx.interaction)


@bot.slash_command(name="재생", description="유튜브에서 바로 검색해서 재생합니다")
@option("제목", description="검색할 노래 제목")
async def play_cmd(ctx: discord.ApplicationContext, 제목: str):
    if not ctx.author.voice or not ctx.author.voice.channel:
        return await ctx.respond("❌ 먼저 통화방에 들어가주세요!", ephemeral=True)

    await ctx.defer()
    channel = ctx.author.voice.channel
    vc = ctx.guild.voice_client

    if vc is None:
        vc = await channel.connect()
    elif vc.channel != channel:
        await vc.move_to(channel)

    results = await search_youtube(제목, count=1)
    if not results:
        return await ctx.followup.send("❌ 검색 결과를 찾지 못했어요.", ephemeral=True)

    info = await extract_stream_url(results[0].get("webpage_url") or results[0].get("url"))
    if not info:
        return await ctx.followup.send("❌ 재생 URL 추출 실패.", ephemeral=True)
    info["url"] = get_best_stream(info)

    state = get_state(ctx.guild_id)
    state["queue"].append(info)

    if not vc.is_playing() and not vc.is_paused():
        await play_next(ctx.guild)

    view = build_panel_view(ctx.guild_id)
    if state["panel_msg"]:
        await state["panel_msg"].edit(view=view)
        await ctx.followup.send(f"✅ **{info['title']}** 추가!", ephemeral=True)
    else:
        msg = await ctx.followup.send(
            view=view,
            flags=discord.MessageFlags(is_components_v2=True),
        )
        state["panel_msg"] = msg


@bot.slash_command(name="대기열", description="현재 재생 대기열을 확인합니다")
async def queue_cmd(ctx: discord.ApplicationContext):
    state = get_state(ctx.guild_id)
    cur = state["current"]
    queue = state["queue"]

    if not cur and not queue:
        return await ctx.respond("📋 대기열이 비어있어요!", ephemeral=True)

    container = discord.ui.Container(accent_colour=discord.Colour.blurple())
    lines = ["## 📋 재생 대기열\n"]
    if cur:
        lines.append(f"🎵 **지금 재생:** {cur['title']}　({fmt_dur(cur.get('duration'))})")
    for i, item in enumerate(queue, 1):
        lines.append(f"`{i}.` {item['title']}　({fmt_dur(item.get('duration'))})")
    container.add_item(discord.ui.TextDisplay("\n".join(lines)))

    view = discord.ui.View(timeout=30)
    view.add_item(container)
    await ctx.respond(
        view=view,
        ephemeral=True,
        flags=discord.MessageFlags(is_components_v2=True),
    )


# ══════════════════════════════════════════════════════
#  봇 시작
# ══════════════════════════════════════════════════════
@bot.event
async def on_ready():
    print(f"✅ {bot.user} 준비 완료 | 컴포넌트 v2 활성화")

bot.run(TOKEN)
