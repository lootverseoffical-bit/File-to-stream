# app.py (THE REAL, FINAL, CLEAN, COMPLETE, FIXED VERSION)

import os
import asyncio
import secrets
import traceback
import uvicorn
import re
import logging
import math
from contextlib import asynccontextmanager

from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, ChatMemberUpdated
from pyrogram.errors import FloodWait, UserNotParticipant
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pyrogram.file_id import FileId
from pyrogram import raw
from pyrogram.session import Session, Auth

# Project ki dusri files se important cheezein import karo
from config import Config
from database import db

# =====================================================================================
# --- SETUP: BOT, WEB SERVER, AUR LOGGING ---
# =====================================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Yeh function bot ko web server ke saath start aur stop karta hai.
    """
    print("--- Lifespan: Server chalu ho raha hai... ---")
    
    # Database connection
    try:
        await db.connect()
        if not db._connected:
            print("⚠️ WARNING: Database connection failed. Links will not be saved permanently.")
    except Exception as e:
        print(f"⚠️ WARNING: Database connection error: {e}")
    
    try:
        print("Starting main Pyrogram bot...")
        await bot.start()
        
        me = await bot.get_me()
        Config.BOT_USERNAME = me.username
        print(f"✅ Main Bot [@{Config.BOT_USERNAME}] safaltapoorvak start ho gaya.")

        # --- MULTI-CLIENT STARTUP ---
        multi_clients[0] = bot
        work_loads[0] = 0
        await initialize_clients()
        
        # Verify storage channel
        if Config.STORAGE_CHANNEL:
            try:
                print(f"Verifying storage channel ({Config.STORAGE_CHANNEL})...")
                await bot.get_chat(Config.STORAGE_CHANNEL)
                print("✅ Storage channel accessible hai.")
            except Exception as e:
                print(f"!!! ERROR: Storage channel not accessible: {e}")
                print("!!! Bot will not work without a valid storage channel!")
        else:
            print("!!! ERROR: STORAGE_CHANNEL not configured in .env file!")
            print("!!! Bot will not work without a storage channel!")

        # Verify force sub channel (optional)
        if Config.FORCE_SUB_CHANNEL:
            try:
                print(f"Verifying force sub channel ({Config.FORCE_SUB_CHANNEL})...")
                await bot.get_chat(Config.FORCE_SUB_CHANNEL)
                print("✅ Force Sub channel accessible hai.")
            except Exception as e:
                print(f"!!! WARNING: Bot, Force Sub channel mein admin nahi hai. Error: {e}")
        
        # Cleanup channel if configured
        if Config.STORAGE_CHANNEL:
            try:
                await cleanup_channel(bot)
            except Exception as e:
                print(f"Warning: Channel cleanup fail ho gaya. Error: {e}")

        print("--- Lifespan: Startup safaltapoorvak poora hua. ---")
    
    except Exception as e:
        print(f"!!! FATAL ERROR: Bot startup ke dauraan error aa gaya: {traceback.format_exc()}")
    
    yield
    
    print("--- Lifespan: Server band ho raha hai... ---")
    if bot.is_initialized:
        await bot.stop()
    await db.disconnect()
    print("--- Lifespan: Shutdown poora hua. ---")

app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- LOG FILTER: YEH SIRF /dl/ WALE LOGS KO CHUPAYEGA ---
class HideDLFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Agar log message mein "GET /dl/" hai, toh usse mat dikhao
        return "GET /dl/" not in record.getMessage()

# Uvicorn ke 'access' logger par filter lagao
logging.getLogger("uvicorn.access").addFilter(HideDLFilter())
# --- FIX KHATAM ---

bot = Client("SimpleStreamBot", api_id=Config.API_ID, api_hash=Config.API_HASH, bot_token=Config.BOT_TOKEN, in_memory=True)
multi_clients = {}; work_loads = {}; class_cache = {}

# =====================================================================================
# --- MULTI-CLIENT LOGIC ---
# =====================================================================================

class TokenParser:
    """ Environment variables se MULTI_TOKENs ko parse karta hai. """
    @staticmethod
    def parse_from_env():
        return {
            c + 1: t
            for c, (_, t) in enumerate(
                filter(lambda n: n[0].startswith("MULTI_TOKEN"), sorted(os.environ.items()))
            )
        }

async def start_client(client_id, bot_token):
    """ Ek naye client bot ko start karta hai. """
    try:
        print(f"Attempting to start Client: {client_id}")
        client = await Client(
            name=str(client_id), 
            api_id=Config.API_ID, 
            api_hash=Config.API_HASH,
            bot_token=bot_token, 
            no_updates=True, 
            in_memory=True
        ).start()
        work_loads[client_id] = 0
        multi_clients[client_id] = client
        print(f"✅ Client {client_id} started successfully.")
    except Exception as e:
        print(f"!!! CRITICAL ERROR: Failed to start Client {client_id} - Error: {e}")

async def initialize_clients():
    """ Saare additional clients ko initialize karta hai. """
    all_tokens = TokenParser.parse_from_env()
    if not all_tokens:
        print("No additional clients found. Using default bot only.")
        return
    
    print(f"Found {len(all_tokens)} extra clients. Starting them...")
    tasks = [start_client(i, token) for i, token in all_tokens.items()]
    await asyncio.gather(*tasks)

    if len(multi_clients) > 1:
        print(f"✅ Multi-Client Mode Enabled. Total Clients: {len(multi_clients)}")

# =====================================================================================
# --- HELPER FUNCTIONS ---
# =====================================================================================

def get_readable_file_size(size_in_bytes):
    if not size_in_bytes:
        return '0B'
    power = 1024
    n = 0
    power_labels = {0: 'B', 1: 'KB', 2: 'MB', 3: 'GB'}
    while size_in_bytes >= power and n < len(power_labels) - 1:
        size_in_bytes /= power
        n += 1
    return f"{size_in_bytes:.2f} {power_labels[n]}"

def mask_filename(name: str):
    if not name:
        return "Protected File"
    base, ext = os.path.splitext(name)
    metadata_pattern = re.compile(
        r'((19|20)\d{2}|4k|2160p|1080p|720p|480p|360p|HEVC|x265|BluRay|WEB-DL|HDRip)',
        re.IGNORECASE
    )
    match = metadata_pattern.search(base)
    if match:
        title_part = base[:match.start()].strip(' .-_')
        metadata_part = base[match.start():]
    else:
        title_part = base
        metadata_part = ""
    masked_title = ''.join(c if (i % 3 == 0 and c.isalnum()) else ('*' if c.isalnum() else c) for i, c in enumerate(title_part))
    return f"{masked_title} {metadata_part}{ext}".strip()

# =====================================================================================
# --- PYROGRAM BOT HANDLERS ---
# =====================================================================================

@bot.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    
    if not Config.STORAGE_CHANNEL:
        await message.reply_text("❌ Bot is not configured properly. Please contact admin.")
        return
    
    if len(message.command) > 1 and message.command[1].startswith("verify_"):
        unique_id = message.command[1].split("_", 1)[1]
        
        # Force subscribe check
        if Config.FORCE_SUB_CHANNEL:
            try:
                member = await client.get_chat_member(Config.FORCE_SUB_CHANNEL, user_id)
                if member.status in [enums.ChatMemberStatus.LEFT, enums.ChatMemberStatus.RESTRICTED]:
                    raise UserNotParticipant
            except UserNotParticipant:
                channel_username = str(Config.FORCE_SUB_CHANNEL).replace('@', '')
                channel_link = f"https://t.me/{channel_username}"
                join_button = InlineKeyboardButton("📢 Join Channel", url=channel_link)
                retry_button = InlineKeyboardButton("✅ Joined", url=f"https://t.me/{Config.BOT_USERNAME}?start={message.command[1]}")
                keyboard = InlineKeyboardMarkup([[join_button], [retry_button]])
                await message.reply_text(
                    "**You Must Join Our Channel To Get The Link!**\n\n"
                    "__Join Channel & Click '✅ Joined'.__",
                    reply_markup=keyboard, quote=True
                )
                return
            except Exception as e:
                print(f"Force sub check error: {e}")
                # Continue anyway if there's an error

        # Check if link exists in database
        msg_id = await db.get_link(unique_id)
        if not msg_id:
            await message.reply_text("❌ Invalid or expired link!", quote=True)
            return
        
        final_link = f"{Config.BASE_URL}/show/{unique_id}"
        reply_text = f"__✅ Verification Successful!\n\nCopy Link:__ `{final_link}`"
        button = InlineKeyboardMarkup([[InlineKeyboardButton("Open Link", url=final_link)]])
        await message.reply_text(reply_text, reply_markup=button, quote=True, disable_web_page_preview=True)

    else:
        reply_text = f"""
👋 **Hello, {user_name}!**

__Welcome To Sharing Box Bot. I Can Help You Create Permanent, Shareable Links For Your Files.__

**How To Use Me:**

__Just Send Or Forward Any File To Me And I will instantly give you a special link that you can share with anyone!__
"""
        await message.reply_text(reply_text)

async def handle_file_upload(message: Message, user_id: int):
    try:
        if not Config.STORAGE_CHANNEL:
            await message.reply_text("❌ Bot is not configured properly. Please contact admin.")
            return
            
        sent_message = await message.copy(chat_id=Config.STORAGE_CHANNEL)
        unique_id = secrets.token_urlsafe(8)
        await db.save_link(unique_id, sent_message.id)
        
        verify_link = f"https://t.me/{Config.BOT_USERNAME}?start=verify_{unique_id}"
        button = InlineKeyboardMarkup([[InlineKeyboardButton("Get Link Now", url=verify_link)]])
        
        await message.reply_text("__✅ File Uploaded!__", reply_markup=button, quote=True)
    except FloodWait as e:
        await asyncio.sleep(e.value)
        await handle_file_upload(message, user_id)
    except Exception as e:
        print(f"!!! ERROR: {traceback.format_exc()}")
        await message.reply_text("❌ Sorry, something went wrong. Please try again later.", quote=True)

@bot.on_message(filters.private & (filters.document | filters.video | filters.audio))
async def file_handler(_, message: Message):
    await handle_file_upload(message, message.from_user.id)

@bot.on_chat_member_updated(filters.chat(Config.STORAGE_CHANNEL))
async def simple_gatekeeper(c: Client, m_update: ChatMemberUpdated):
    if not Config.STORAGE_CHANNEL:
        return
    try:
        if(m_update.new_chat_member and m_update.new_chat_member.status==enums.ChatMemberStatus.MEMBER):
            u=m_update.new_chat_member.user
            if u.id==Config.OWNER_ID or u.is_self: return
            print(f"Gatekeeper: Kicking {u.id}")
            await c.ban_chat_member(Config.STORAGE_CHANNEL,u.id)
            await c.unban_chat_member(Config.STORAGE_CHANNEL,u.id)
    except Exception as e:
        print(f"Gatekeeper Error: {e}")

async def cleanup_channel(c: Client):
    if not Config.STORAGE_CHANNEL:
        return
    print("Gatekeeper: Running cleanup...")
    allowed={Config.OWNER_ID,c.me.id}
    try:
        async for m in c.get_chat_members(Config.STORAGE_CHANNEL):
            if m.user.id in allowed:
                continue
            if m.status in [enums.ChatMemberStatus.ADMINISTRATOR,enums.ChatMemberStatus.OWNER]:
                continue
            try:
                print(f"Cleanup: Kicking {m.user.id}")
                await c.ban_chat_member(Config.STORAGE_CHANNEL,m.user.id)
                await asyncio.sleep(1)
            except FloodWait as e:
                await asyncio.sleep(e.value)
            except Exception as e:
                print(f"Cleanup Error: {e}")
    except Exception as e:
        print(f"Cleanup Error: {e}")

# =====================================================================================
# --- FASTAPI WEB SERVER ---
# =====================================================================================
 
@app.get("/")
async def health_check():
    """
    This route provides a 200 OK response for uptime monitors.
    """
    return {"status": "ok", "message": "Server is healthy and running!"}

@app.get("/show/{unique_id}", response_class=HTMLResponse)
async def show_page(request: Request, unique_id: str):
    """
    Display the file download page with all details.
    This fetches file info from database and renders the page.
    """
    try:
        # Get message ID from database
        message_id = await db.get_link(unique_id)
        if not message_id:
            raise HTTPException(status_code=404, detail="Link expired or invalid.")
        
        # Get main bot
        main_bot = multi_clients.get(0)
        if not main_bot:
            raise HTTPException(status_code=503, detail="Bot is not ready yet. Please try again later.")
        
        # Fetch message from storage channel
        try:
            message = await main_bot.get_messages(Config.STORAGE_CHANNEL, message_id)
        except Exception:
            raise HTTPException(status_code=404, detail="File not found on Telegram.")
        
        # Extract media
        media = message.document or message.video or message.audio
        if not media:
            raise HTTPException(status_code=404, detail="Media not found in the message.")
        
        # Prepare file details
        original_file_name = media.file_name or "file"
        safe_file_name = "".join(c for c in original_file_name if c.isalnum() or c in (' ', '.', '_', '-')).rstrip()
        mime_type = media.mime_type or "application/octet-stream"
        
        # Get base URL with fallback
        base_url = Config.BASE_URL or "http://localhost:8000"
        
        context = {
            "request": request,
            "file_name": mask_filename(original_file_name),
            "file_size": get_readable_file_size(media.file_size),
            "is_media": mime_type.startswith(("video", "audio")),
            "direct_dl_link": f"{base_url}/dl/{message_id}/{safe_file_name}",
            "mx_player_link": f"intent:{base_url}/dl/{message_id}/{safe_file_name}#Intent;action=android.intent.action.VIEW;type={mime_type};end",
            "vlc_player_link": f"intent:{base_url}/dl/{message_id}/{safe_file_name}#Intent;action=android.intent.action.VIEW;type={mime_type};package=org.videolan.vlc;end"
        }
        
        return templates.TemplateResponse("show.html", context)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in /show route: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Internal server error.")

@app.get("/api/file/{unique_id}", response_class=JSONResponse)
async def get_file_details_api(request: Request, unique_id: str):
    """
    API endpoint to get file details as JSON.
    """
    try:
        message_id = await db.get_link(unique_id)
        if not message_id:
            raise HTTPException(status_code=404, detail="Link expired or invalid.")
        
        main_bot = multi_clients.get(0)
        if not main_bot:
            raise HTTPException(status_code=503, detail="Bot is not ready.")
        
        try:
            message = await main_bot.get_messages(Config.STORAGE_CHANNEL, message_id)
        except Exception:
            raise HTTPException(status_code=404, detail="File not found on Telegram.")
        
        media = message.document or message.video or message.audio
        if not media:
            raise HTTPException(status_code=404, detail="Media not found in the message.")
        
        file_name = media.file_name or "file"
        safe_file_name = "".join(c for c in file_name if c.isalnum() or c in (' ', '.', '_', '-')).rstrip()
        mime_type = media.mime_type or "application/octet-stream"
        base_url = Config.BASE_URL or "http://localhost:8000"
        
        response_data = {
            "file_name": mask_filename(file_name),
            "file_size": get_readable_file_size(media.file_size),
            "file_size_bytes": media.file_size,
            "mime_type": mime_type,
            "is_media": mime_type.startswith(("video", "audio")),
            "direct_dl_link": f"{base_url}/dl/{message_id}/{safe_file_name}",
            "mx_player_link": f"intent:{base_url}/dl/{message_id}/{safe_file_name}#Intent;action=android.intent.action.VIEW;type={mime_type};end",
            "vlc_player_link": f"intent:{base_url}/dl/{message_id}/{safe_file_name}#Intent;action=android.intent.action.VIEW;type={mime_type};package=org.videolan.vlc;end"
        }
        return JSONResponse(content=response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in /api/file: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Internal server error.")

class ByteStreamer:
    """Handles streaming of files from Telegram."""
    
    def __init__(self, client: Client):
        self.client = client
    
    @staticmethod
    async def get_location(file_id: FileId):
        """Get file location for Telegram API."""
        # Fix: Handle missing thumbnail_size attribute
        thumb_size = getattr(file_id, 'thumbnail_size', '')
        return raw.types.InputDocumentFileLocation(
            id=file_id.media_id,
            access_hash=file_id.access_hash,
            file_reference=file_id.file_reference,
            thumb_size=thumb_size
        )
    
    async def yield_file(self, file_id: FileId, index: int, offset: int, 
                         first_part_cut: int, last_part_cut: int, 
                         part_count: int, chunk_size: int):
        """Yield file chunks for streaming."""
        client = self.client
        work_loads[index] += 1
        
        # Get or create media session
        media_session = client.media_sessions.get(file_id.dc_id)
        if media_session is None:
            if file_id.dc_id != await client.storage.dc_id():
                auth_key = await Auth(client, file_id.dc_id, await client.storage.test_mode()).create()
                media_session = Session(client, file_id.dc_id, auth_key, 
                                       await client.storage.test_mode(), is_media=True)
                await media_session.start()
                exported_auth = await client.invoke(
                    raw.functions.auth.ExportAuthorization(dc_id=file_id.dc_id)
                )
                await media_session.invoke(
                    raw.functions.auth.ImportAuthorization(id=exported_auth.id, bytes=exported_auth.bytes)
                )
                client.media_sessions[file_id.dc_id] = media_session
            else:
                # Create separate media session for same DC
                auth_key = await Auth(client, file_id.dc_id, await client.storage.test_mode()).create()
                media_session = Session(client, file_id.dc_id, auth_key, 
                                       await client.storage.test_mode(), is_media=True)
                await media_session.start()
                client.media_sessions[file_id.dc_id] = media_session
        
        location = await self.get_location(file_id)
        current_part = 1
        
        try:
            while current_part <= part_count:
                try:
                    r = await media_session.invoke(
                        raw.functions.upload.GetFile(location=location, offset=offset, limit=chunk_size),
                        retries=0
                    )
                except Exception as e:
                    print(f"Error fetching chunk {current_part}: {e}")
                    break
                
                if isinstance(r, raw.types.upload.File):
                    chunk = r.bytes
                    if not chunk:
                        break
                    
                    # Handle edge cases for partial chunks
                    if part_count == 1:
                        yield chunk[first_part_cut:last_part_cut]
                    elif current_part == 1:
                        yield chunk[first_part_cut:]
                    elif current_part == part_count:
                        yield chunk[:last_part_cut]
                    else:
                        yield chunk
                    
                    current_part += 1
                    offset += chunk_size
                else:
                    break
        finally:
            work_loads[index] -= 1

@app.get("/dl/{msg_id}/{file_name}")
async def stream_media(request: Request, msg_id: int, file_name: str):
    """
    Stream the file with support for range requests (partial content).
    """
    try:
        # Check if any clients are available
        if not work_loads:
            raise HTTPException(status_code=503, detail="No workers available.")
        
        # Pick client with least workload
        client_id = min(work_loads, key=work_loads.get)
        client = multi_clients.get(client_id)
        if not client:
            raise HTTPException(status_code=503, detail="No available clients.")
        
        # Get or create streamer
        streamer = class_cache.get(client)
        if not streamer:
            streamer = ByteStreamer(client)
            class_cache[client] = streamer
        
        # Fetch message
        try:
            message = await client.get_messages(Config.STORAGE_CHANNEL, msg_id)
        except Exception:
            raise HTTPException(status_code=404, detail="Message not found.")
        
        # Get media
        media = message.document or message.video or message.audio
        if not media or message.empty:
            raise HTTPException(status_code=404, detail="File not found.")
        
        # Decode file ID
        file_id = FileId.decode(media.file_id)
        file_size = media.file_size
        
        # Parse range header
        range_header = request.headers.get("Range", "")
        from_bytes, until_bytes = 0, file_size - 1
        
        if range_header:
            try:
                range_str = range_header.replace("bytes=", "")
                if "-" in range_str:
                    parts = range_str.split("-")
                    from_bytes = int(parts[0]) if parts[0] else 0
                    until_bytes = int(parts[1]) if parts[1] and parts[1] else file_size - 1
            except (ValueError, IndexError):
                pass
        
        # Validate range
        if until_bytes >= file_size or from_bytes < 0:
            raise HTTPException(status_code=416, detail="Requested range not satisfiable")
        
        # Calculate streaming parameters
        req_length = until_bytes - from_bytes + 1
        chunk_size = 1024 * 1024  # 1 MB
        offset = (from_bytes // chunk_size) * chunk_size
        first_part_cut = from_bytes - offset
        last_part_cut = (until_bytes % chunk_size) + 1
        part_count = math.ceil(req_length / chunk_size)
        
        # Generate stream
        body = streamer.yield_file(
            file_id, client_id, offset, first_part_cut, 
            last_part_cut, part_count, chunk_size
        )
        
        # Prepare headers
        status_code = 206 if range_header else 200
        headers = {
            "Content-Type": media.mime_type or "application/octet-stream",
            "Accept-Ranges": "bytes",
            "Content-Disposition": f'inline; filename="{media.file_name or "file"}"',
            "Content-Length": str(req_length),
            "Cache-Control": "no-cache"
        }
        
        if range_header:
            headers["Content-Range"] = f"bytes {from_bytes}-{until_bytes}/{file_size}"
        
        return StreamingResponse(content=body, status_code=status_code, headers=headers)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in /dl route: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Internal streaming error.")

# =====================================================================================
# --- MAIN EXECUTION BLOCK ---
# =====================================================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    # Log level ko "info" rakho taaki hamara filter kaam kar sake
    uvicorn.run("app:app", host="0.0.0.0", port=port, log_level="info")
