import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import aiohttp
import mysql.connector
from mysql.connector import pooling
import openai
import PyPDF2
import docx
import io
from openai import OpenAI
import os
import json
import re
from typing import Optional, List, Dict
from datetime import datetime
import logging
from pydantic import BaseModel
from typing import List

import requests
from bs4 import BeautifulSoup





# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('discord_bot')

# Configuration
class Config:
    """config class to store all config"""
    DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    DB_CONFIG = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'user': os.getenv('DB_USER', 'root'),
        'password': os.getenv('DB_PASSWORD', ''),
        'database': os.getenv('DB_NAME', 'discord_resource_bot')
    }
    GROUP_THEME = os.getenv('GROUP_THEME', 'Technology and Programming')  # Configure per server
    MAX_DOCUMENT_TOKENS = 1000  # Initial tokens for document relevance check

# Initialize OpenAI
api_key = Config.OPENAI_API_KEY

class Keyword(BaseModel):
    """output class for Openai calls"""
    keyword_list : List[str]
    

class DatabaseManager:
    """Database class for all the sql files"""
    def __init__(self):
        self.pool = mysql.connector.pooling.MySQLConnectionPool(
            pool_name="discord_bot_pool",
            pool_size=5,
            pool_reset_session=True,
            **Config.DB_CONFIG
        )
        self.init_database()
    
    def init_database(self):
        """Initialize database tables"""
        conn = self.pool.get_connection()
        cursor = conn.cursor()
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                discord_id BIGINT PRIMARY KEY,
                discord_username VARCHAR(255),
                server_id BIGINT,
                job_title VARCHAR(255),
                skills TEXT,
                interests TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_server (server_id)
            )
        ''')
        
        # Server configurations table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS server_configs (
                server_id BIGINT PRIMARY KEY,
                theme VARCHAR(500),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Resources tracking table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS resources (
                id INT AUTO_INCREMENT PRIMARY KEY,
                server_id BIGINT,
                message_id BIGINT,
                resource_type VARCHAR(50),
                resource_url TEXT,
                resource_summary TEXT,
                tagged_users TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_server_resource (server_id)
            )
        ''')
        
        conn.commit()
        cursor.close()
        conn.close()
    
    def save_user(self, discord_id, discord_username, server_id, job_title, skills, interests):
        """Save or update user profile"""
        conn = self.pool.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO users (discord_id, discord_username, server_id, job_title, skills, interests)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
            discord_username = VALUES(discord_username),
            job_title = VALUES(job_title),
            skills = VALUES(skills),
            interests = VALUES(interests),
            updated_at = CURRENT_TIMESTAMP
        ''', (discord_id, discord_username, server_id, job_title, skills, interests))
        
        conn.commit()
        cursor.close()
        conn.close()
    
    def get_user(self, discord_id, server_id):
        """Get user profile"""
        conn = self.pool.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute('''
            SELECT * FROM users WHERE discord_id = %s AND server_id = %s
        ''', (discord_id, server_id))
        
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        return user
    
    def get_all_users(self, server_id):
        """Get all users in a server"""
        conn = self.pool.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute('''
            SELECT * FROM users WHERE server_id = %s
        ''', (server_id,))
        
        users = cursor.fetchall()
        cursor.close()
        conn.close()
        return users
    
    def get_skills(self, server_id):
        """get skills of all users in a server"""
        conn = self.pool.get_connection()
        cursor = conn.cursor(dictionary = True)
        cursor.execute(
            '''
SELECT skills FROM users WHERE server_id = %s

''', (server_id,)
        )
        skills = cursor.fetchall()
        cursor.close()
        conn.close()
        return skills
    
    def save_server_theme(self, server_id, theme):
        """Save server theme configuration"""
        conn = self.pool.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO server_configs (server_id, theme)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE theme = VALUES(theme)
        ''', (server_id, theme))
        
        conn.commit()
        cursor.close()
        conn.close()
    
    def get_server_theme(self, server_id):
        """Get server theme"""
        conn = self.pool.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT theme FROM server_configs WHERE server_id = %s
        ''', (server_id,))
        
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        return result[0] if result else Config.GROUP_THEME
    




# Resource Analyzer
class ResourceAnalyzer:
    """core discord logic"""
    client = OpenAI(
                api_key = api_key
            )
    @staticmethod
    async def extract_text_from_document(attachment):
        """Extract text from document attachments"""
        try:
            file_bytes = await attachment.read()
            file_stream = io.BytesIO(file_bytes)
            
            if attachment.filename.lower().endswith('.pdf'):
                pdf_reader = PyPDF2.PdfReader(file_stream)
                text = ""
                for page in pdf_reader.pages:  # Limit to first 5 pages
                    text += page.extract_text()
                return text[:300000]  # Limit characters
            
            elif attachment.filename.lower().endswith(('.docx', '.doc')):
                doc = docx.Document(file_stream)
                text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
                return text[:300000]
            
            elif attachment.filename.lower().endswith(('.txt', '.md')):
                return file_bytes.decode('utf-8', errors='ignore')[:300000]
            
        except Exception as e:
            logger.error(f"Error extracting text from document: {e}")
            return None
    
    @staticmethod
    async def check_document_similarity(text, master_keyword):
        """Check if content is relevant to group theme using GPT"""
        try:
            response = await ResourceAnalyzer.client.responses.parse(
                    model="gpt-5-mini",
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are a technically skilled engineer. Your task is to analyze the given text and identify "
                                "which skills or interests from a provided list are explicitly mentioned or can be logically inferred. "
                                "Focus only on relevant technical or professional keywords. "
                                "Return only the matching skills from the provided list — no explanations or extra commentary."
                            )
                        },
                        {
                            "role": "user",
                            "content": (
                                f"The following is the text to analyze:\n\n{text}\n\n"
                                f"Here is the complete list of skills and interests available on the server:\n{master_keyword}\n\n"
                                "Return only the matched skills as plain text or a clean list."
                            )
                        }
                    ],
                    text_format=Keyword
            )
            
            result = response.output_parsed()
            return result.keyword_list
        except Exception as e:
            logger.error(f"Error checking relevance: {e}")
            return ""
    

    @staticmethod
    async def get_web_content(url:str, master_keyword):
        """ this is to get web content """

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                content = await response.text() 
        soup = BeautifulSoup(content , "html.parser")
        response = await ResourceAnalyzer.client.responses.parse(
            model="gpt-5-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a technically skilled engineer. Your task is to analyze the given HTML content and identify "
                        "which skills or interests from a provided list are explicitly present or can be reasonably inferred "
                        "from the HTML. Focus on relevant technical and domain-specific keywords. "
                        "Return only the matching skills from the provided list."
                    )
                },
                {
                    "role": "user",
                    "content": (
                        f"The following is the HTML content:\n\n{soup.prettify()}\n\n"
                        f"Here is the list of skills and interests to compare against:\n{master_keyword}\n\n"
                        "Return only the matched skills as plain text or a clean list. Do not include explanations."
                    )
                }
            ],
            text_format=Keyword
        )
        output_keyword = response.output_parsed
        return output_keyword.keyword_list


    
    @staticmethod
    async def match_users_to_resource( users_data, keyword_list):
        """Match users to resource using GPT"""
        try:
            matched_user_ids = []
            users_profiles = {}
            for user in users_data:
                users_profiles[user['discord_id']] =  user['skills'].lower(),
    
            for matched_skill in keyword_list:
                for user, skill in users_profiles.items():
                    if matched_skill.lower() in skill:
                        matched_user_ids.append(user)

            return matched_user_ids
        except Exception as e:
            logger.error(f"Error matching users: {e}")
            return []




# Registration Modal
class RegistrationModal(discord.ui.Modal, title='Profile Registration'):
    job_title = discord.ui.TextInput(
        label='Job Title',
        placeholder='e.g., Software Engineer, Data Scientist',
        required=True,
        max_length=100
    )
    
    skills = discord.ui.TextInput(
        label='Skills',
        placeholder='e.g., Python, React, Machine Learning, AWS',
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=500
    )
    
    interests = discord.ui.TextInput(
        label='Interests',
        placeholder='e.g., Web Development, AI, DevOps, Open Source',
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=500
    )
    
    def __init__(self, db_manager):
        super().__init__()
        self.db_manager = db_manager
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        self.db_manager.save_user(
            discord_id=interaction.user.id,
            discord_username=str(interaction.user),
            server_id=interaction.guild_id,
            job_title=self.job_title.value,
            skills=self.skills.value,
            interests=self.interests.value
        )
        
        embed = discord.Embed(
            title="✅ Profile Registered",
            description="Your profile has been saved successfully!",
            color=discord.Color.green()
        )
        embed.add_field(name="Job Title", value=self.job_title.value, inline=False)
        embed.add_field(name="Skills", value=self.skills.value, inline=False)
        embed.add_field(name="Interests", value=self.interests.value, inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)



# Main Bot Class
class ResourceBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        
        super().__init__(command_prefix='!', intents=intents)
        self.db_manager = DatabaseManager()
        self.analyzer = ResourceAnalyzer()
    
    async def setup_hook(self):
        await self.tree.sync()
        logger.info("Slash commands synced")
    
    async def on_ready(self):
        logger.info(f'{self.user} has connected to Discord!')
    
    async def on_message(self, message):
        # Ignore bot messages
        if message.author.bot:
            return
        
        # Check for resources in messages
        await self.check_for_resources(message)
        
        await self.process_commands(message)
    
    async def check_for_resources(self, message):
        """Check message for resources and tag relevant users"""
        resource_found = False
        master_keyword = self.db_manager.get_skills(message.guild.id)

        
        # Check for links
        url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
        urls = re.findall(url_pattern, message.content)
        keyword_list = []
        
        if urls:
            for url in urls: 
                keyword_list = await self.analyzer.get_web_content(url, master_keyword )
    
        # Check for document attachments
        if not resource_found and message.attachments:
            for attachment in message.attachments:
                if attachment.filename.lower().endswith(('.pdf', '.docx', '.doc', '.txt', '.md')):
                    text = await self.analyzer.extract_text_from_document(attachment)
                    if text:
                        doc_keyword = self.analyzer.check_document_similarity(text, master_keyword)
                        keyword_list.extend(doc_keyword) # type: ignore
        
        if len(keyword_list) != 0 :
            resource_found = True
    
        
        # If resource found, match and tag users
        if resource_found:
            users = self.db_manager.get_all_users(message.guild.id)
            if users:
                matched_user_ids = await self.analyzer.match_users_to_resource(
                     users, keyword_list
                )
                matched_user_ids = list(set(matched_user_ids))
                if matched_user_ids:
                    # Create mention string
                    mentions = []
                    for user_id in matched_user_ids:  # Limit to 10 tags
                        member = message.guild.get_member(int(user_id))
                        if member:
                            mentions.append(member.mention)
                    
                    if mentions:
                        embed = discord.Embed(
                            title="📚 Relevant Resource Detected",
                            description=f"This resource has been found to be relevant for you",
                            color=discord.Color.blue()
                        )
                        embed.add_field(
                            name="Relevant for",
                            value=" ".join(mentions),
                            inline=False
                        )
                        embed.set_footer(text="This resource matches your profile interests/skills")
                        
                        await message.reply(embed=embed)



# Bot Commands
bot = ResourceBot()

@bot.tree.command(name="register", description="Register or update your profile")
async def register(interaction: discord.Interaction):
    modal = RegistrationModal(bot.db_manager)
    await interaction.response.send_modal(modal)

@bot.tree.command(name="profile", description="View your profile")
async def profile(interaction: discord.Interaction):
    user = bot.db_manager.get_user(interaction.user.id, interaction.guild_id)
    
    if not user:
        await interaction.response.send_message(
            "❌ You haven't registered yet! Use `/register` to create your profile.",
            ephemeral=True
        )
        return
    
    embed = discord.Embed(
        title=f"Profile: {interaction.user.display_name}",
        color=discord.Color.blue()
    )
    embed.add_field(name="Job Title", value=user['job_title'], inline=False)
    embed.add_field(name="Skills", value=user['skills'], inline=False)
    embed.add_field(name="Interests", value=user['interests'], inline=False)
    embed.set_footer(text=f"Last updated: {user['updated_at']}")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="edit_profile", description="Edit your existing profile")
async def edit_profile(interaction: discord.Interaction):
    user = bot.db_manager.get_user(interaction.user.id, interaction.guild_id)
    
    if not user:
        await interaction.response.send_message(
            "❌ You need to register first! Use `/register` to create your profile.",
            ephemeral=True
        )
        return
    
    # Create modal with existing data
    modal = RegistrationModal(bot.db_manager)
    modal.job_title.default = user['job_title']
    modal.skills.default = user['skills']
    modal.interests.default = user['interests']
    
    await interaction.response.send_modal(modal)

@bot.tree.command(name="set_theme", description="Set the server's theme (Admin only)")
@app_commands.checks.has_permissions(administrator=True)
async def set_theme(interaction: discord.Interaction, theme: str):
    bot.db_manager.save_server_theme(interaction.guild_id, theme)
    
    embed = discord.Embed(
        title="✅ Theme Updated",
        description=f"Server theme set to: **{theme}**",
        color=discord.Color.green()
    )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="stats", description="View bot statistics for this server")
async def stats(interaction: discord.Interaction):
    users = bot.db_manager.get_all_users(interaction.guild_id)
    theme = bot.db_manager.get_server_theme(interaction.guild_id)
    
    embed = discord.Embed(
        title="📊 Server Statistics",
        color=discord.Color.blue()
    )
    embed.add_field(name="Registered Users", value=len(users), inline=True)
    embed.add_field(name="Server Theme", value=theme, inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# Error Handler
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "❌ You don't have permission to use this command.",
            ephemeral=True
        )
    else:
        logger.error(f"Error: {error}")
        await interaction.response.send_message(
            "❌ An error occurred while processing your command.",
            ephemeral=True
        )



# Run the bot
if __name__ == "__main__":
    bot.run(Config.DISCORD_TOKEN)