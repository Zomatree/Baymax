""" Basic 'get_streams' kinda deal. """
import datetime
import typing

import asyncpg
import discord
from discord.ext import commands, tasks

from utils import db


class TwitchTable(db.Table):
    """ Create the twitch database table. """
    id = db.PrimaryKeyColumn()

    guild_id = db.Column(db.Integer(big=True))
    channel_id = db.Column(db.Integer(big=True))
    streamer_name = db.Column(db.String)
    streamer_last_game = db.Column(db.String())
    streamer_last_datetime = db.Column(db.Datetime())


class Twitch(commands.Cog):
    """ Twitch based stuff on discord! """

    def __init__(self, bot):
        """ Classic init function. """
        self.bot = bot
        self.stream_endpoint = "https://api.twitch.tv/helix/streams"
        self.user_endpoint = "https://api.twitch.tv/helix/users"
        self.game_endpoint = "https://api.twitch.tv/helix/games"
        self.get_streamers.start()

    async def _get_streamers(self, name: str) -> asyncpg.Record:
        """ To get all streamers in the db. """
        query = """ SELECT * FROM twitchtable WHERE streamer_name = $1; """
        return await self.bot.pool.fetch(query, name)

    async def _get_streamer_guilds(self, guild_id: int) -> asyncpg.Record:
        """ Return records for matched guild_ids. """
        query = """ SELECT * FROM twitchtable WHERE guild_id = $1; """
        return await self.bot.pool.fetch(query, guild_id)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        """ Let's not post streamers to dead guilds. """
        records = await self._get_streamer_guilds(guild.id)
        if records:
            query = """ DELETE FROM twitchtable WHERE guild_id = $1; """
            await self.bot.pool.execute(query, guild.id)

    @commands.group(invoke_without_command=True)
    async def twitch(self, ctx: commands.Context) -> discord.Message:
        """ Twitch main command. """
        if not ctx.invoked_subcommand:
            return await ctx.send("You require more arguments for this command.")

    @twitch.command(hidden=True)
    @commands.is_owner()
    async def streamdb(self, ctx: commands.Context) -> None:
        query = """SELECT * FROM twitchtable;"""
        results = await self.bot.pool.fetch(query)
        for item in results:
            await ctx.send(f"{item['guild_id']} -> {item['channel_id']} -> {item['streamer_name']} -> {(datetime.datetime.utcnow() - item['streamer_last_datetime']).seconds}")

    @twitch.command(name="add")
    @commands.has_guild_permissions(manage_channels=True)
    async def add_streamer(self, ctx, name: str, channel: discord.TextChannel = None) -> typing.Union[discord.Reaction, discord.Message]:
        """ Add a streamer to the database for polling. """
        channel = channel or ctx.channel
        results = await self._get_streamers(name)
        if results:
            return await ctx.send("This streamer is already monitored.")
        query = """ INSERT INTO twitchtable (guild_id, channel_id, streamer_name, streamer_last_datetime) VALUES ($1, $2, $3, $4); """
        await self.bot.pool.execute(query, ctx.guild.id, channel.id, name, (datetime.datetime.utcnow() - datetime.timedelta(hours=3)))
        return await ctx.message.add_reaction(":TickYes:672157420574736386")

    @tasks.loop(minutes=5.0)
    async def get_streamers(self) -> None:
        """ Task loop to get the active streamers in the db and post to specified channels. """
        query = """ SELECT * FROM twitchtable; """
        results = await self.bot.pool.fetch(query)
        for item in results:
            if not item['streamer_last_datetime']:
                item['streamer_last_datetime'] = (
                    datetime.datetime.utcnow() - datetime.timedelta(hours=3))
            guild = self.bot.get_guild(item['guild_id'])
            channel = guild.get_channel(item['channel_id'])
            async with self.bot.session.get(self.stream_endpoint,
                                            params={
                                                "user_login": f"{item['streamer_name']}"},
                                            headers=self.bot.config.twitch_headers) as resp:
                stream_json = await resp.json()
            if stream_json['data'] == []:
                continue
            current_stream = datetime.datetime.utcnow() - \
                item['streamer_last_datetime']
            if ((stream_json['data'][0]['title'] != item['streamer_last_game'])
                    or (current_stream.seconds >= 7200)):
                embed = discord.Embed(
                    title=f"{item['streamer_name']} is live with: {stream_json['data'][0]['title']}",
                    colour=discord.Colour.blurple(),
                    url=f"https://twitch.tv/{item['streamer_name']}")
                async with self.bot.session.get(self.game_endpoint,
                                                params={
                                                    "id": f"{stream_json['data'][0]['game_id']}"},
                                                headers=self.bot.config.twitch_headers) as game_resp:
                    game_json = await game_resp.json()
                async with self.bot.session.get(self.user_endpoint,
                                                params={
                                                    "id": stream_json['data'][0]['user_id']},
                                                headers=self.bot.config.twitch_headers) as user_resp:
                    user_json = await user_resp.json()
                embed.set_author(name=stream_json['data'][0]['user_name'],
                                 icon_url=f"{user_json['data'][0]['profile_image_url']}")
                embed.add_field(
                    name="Game", value=f"{game_json['data'][0]['name']}", inline=True)
                embed.add_field(name="Viewers",
                                value=f"{stream_json['data'][0]['viewer_count']}", inline=True)
                embed.set_image(url=stream_json['data'][0]['thumbnail_url'].replace(
                    "{width}", "600").replace("{height}", "400"))
                message = await channel.send(f"{item['streamer_name']} is now live!", embed=embed)
                insert_query = """ UPDATE twitchtable SET streamer_last_game = $1, streamer_last_datetime = $2 WHERE streamer_name = $3; """
                await self.bot.pool.execute(insert_query, stream_json['data'][0]['title'], message.created_at, item['streamer_name'])


def cog_unload(self):
    """ When the cog is unloaded, we wanna kill the task. """
    self.get_streamers.cancel()


def setup(bot):
    """ Setup the cog & extension. """
    bot.add_cog(Twitch(bot))
