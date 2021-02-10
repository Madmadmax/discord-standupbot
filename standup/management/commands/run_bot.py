import asyncio
import logging

from django.core.management.base import BaseCommand
from discord.ext.commands import Bot, MemberConverter, errors
import discord
from django.conf import settings
from django.utils import timezone
import datetime
from standup import models
import pytz


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Runs the Discord Bot'

    def handle(self, *args, **options):
        bot = Bot(command_prefix='!')

        logger.info('-----------------------------------')
        logger.info('Starting the bot...')

        @bot.event
        async def on_ready():
            logger.info('-----------------------------------')
            logger.info(f'Bot logged in as {bot.user.name} ({bot.user.id})')
            logger.info('-----------------------------------')
        
        bot.remove_command('help')

        @bot.command()
        async def standup(ctx):
            try:
                await ctx.message.delete()
            except discord.errors.Forbidden:
                pass

            embed = discord.Embed(
                title="**StandupBot Help**",
                description="These commands are available:"
            )
            embed.add_field(
                name="**!timezones**",
                value="Shows all available timezones to pick from",
                inline=False
            )
            embed.add_field(
                name="**!findtimezone <name>**",
                value="Shows all available timezones to pick from matching the given name, for easier lookup",  # noqa
                inline=False
            )
            embed.add_field(
                name="**!settimezone <tz_name>**",
                value="Set a timezone from the `!timezones` list",
                inline=False
            )
            embed.add_field(
                name="**!mute_until <yyyy/mm/dd>**",
                value="Mute yourself from standup participation until a given date, good for vacations",  # noqa
                inline=False
            )
            embed.add_field(
                name="**!newstandup <standup_type>**",
                value="Start a new standup for the channel you are in",
                inline=False
            )
            embed.add_field(
                name="**!addparticipant <standup_type> [readonly] <user 1> <user 2>...**",  # noqa
                value="Add a new participant for a standup, optionally read only. You can add multiple add the same time",  # noqa
                inline=False
            )
            
            await ctx.author.send(embed=embed)
        
        @bot.command(name='sendsummary')
        async def sendsummary(ctx, standup_type):

            await ctx.message.delete()

            if not ctx.author.permissions_in(ctx.channel).manage_messages:
                await ctx.author.send(
                    'Sorry, you have no permission to do this! '
                    'Only users with the permission to manage messages '
                    'for a given channel can do this.'
                )
                return

            try:
                stype = models.StandupType.objects.get(
                    command_name=standup_type
                )
            except models.StandupType.DoesNotExist:
                msg = (
                    'Please provide a valid standup type as the argument '
                    'of this function, your options are:\n\n'
                )
                msg += '\n'.join([
                    f'`{s.command_name}` ({s.name})'
                    for s in models.StandupType.objects.all()
                ])
                await ctx.author.send(msg)
                return 
            
            today = timezone.now().date()

            standup = models.Standup.objects.filter(
                event__standup_type=stype,
                event__channel__discord_channel_id=ctx.channel.id,
                event__standup_type__publish_to_channel=True,
                standup_date__lt=today
            ).order_by('-id').first()

            if standup:
                await ctx.author.send(f'Sending summary for {standup}')
                await standup.send_summary(bot)
            else:
                await ctx.author.send('Standup not found, can\'t publish!')

        @bot.command(name='addparticipant')
        async def addparticipant(ctx, standup_type, *users):

            await ctx.message.delete()

            users = list(users)
            read_only = False

            if users[0] == 'readonly':
                users.pop(0)
                read_only = True
            
            if not ctx.author.permissions_in(ctx.channel).manage_messages:
                await ctx.author.send(
                    'Sorry, you have no permission to do this! '
                    'Only users with the permission to manage roles '
                    'for a given channel can do this.'
                )
                return

            try:
                stype = models.StandupType.objects.get(
                    command_name=standup_type
                )
            except models.StandupType.DoesNotExist:
                msg = (
                    'Please provide a valid standup type as the argument '
                    'of this function, your options are:\n\n'
                )
                msg += '\n'.join([
                    f'`{s.command_name}` ({s.name})'
                    for s in models.StandupType.objects.all()
                ])
                await ctx.author.send(msg)
                return 

            members = []
            failed = []
            for user in users:
                try:
                    mem = await MemberConverter().convert(ctx, user)
                except errors.BadArgument:
                    continue

                success, reason = (
                    models.StandupEvent.objects.add_participant_from_discord(
                        stype, ctx.channel, mem, ctx.author, read_only
                    )
                )

                if success:
                    members.append(mem)

                if not success:
                    failed.append((mem, reason))

                logger.info(f'{success}, {reason}')
            
            if members:
                mstring = ', '.join([f'<@{x.id}>' for x in members])
                await ctx.send(
                    f'Added {mstring} as participants of this standup!'
                )

            if failed:
                for mem, reason in failed:
                    await ctx.send(
                        f'Failed to add <@{mem.id}> '
                        f'as participants of this standup, {reason}.'
                    )

        @bot.command(name='timezones')
        async def timezones(ctx):

            try:
                await ctx.message.delete()
            except discord.errors.Forbidden:
                pass

            await ctx.author.send(
                '**You can choose from the following timezones:**'
            )
            
            # looping over slices of all timezones, working around max.
            # message length of Discord
            for i in range((len(pytz.common_timezones) // 75) + 1):
                tzs = pytz.common_timezones[i*75:i*75+75]
                msg = f"`{'`, `'.join(tzs)}`"
                await ctx.author.send(msg)

        @bot.command(name='findtimezone')
        async def findtimezone(ctx, name):
            try:
                await ctx.message.delete()
            except discord.errors.Forbidden:
                pass

            await ctx.author.send(
                f'**Found the following timezones for `{name}`:**'
            )
            
            # looping over slices of all timezones, working around max.
            # message length of Discord
            ftzs = [
                x for x in pytz.common_timezones if name.lower() in x.lower()
            ]
            for i in range((len(ftzs) // 75) + 1):
                tzs = ftzs[i*75:i*75+75]
                msg = f"`{'`, `'.join(tzs)}`"
                await ctx.author.send(msg)

        @bot.command(name='settimezone')
        async def settimezone(ctx, timezonename):
            try:
                await ctx.message.delete()
            except discord.errors.Forbidden:
                pass

            if timezonename in pytz.common_timezones:
                user, _ = models.User.objects.get_or_create(
                    discord_id=ctx.author.id, 
                    defaults={
                        'username': ctx.author.id, 
                        'first_name': ctx.author.display_name, 
                        'last_name': ctx.author.discriminator
                    })

                user.timezone = timezonename
                user.save()

                await ctx.author.send(
                    f'Thanks, your timezone has been set to {user.timezone}'
                )
            else:
                await ctx.author.send(
                    f'{timezonename} is a unknown timezone, '
                    f'please execute the `!timezones` command '
                    f'to see all avaiable timezones!'
                )

        @bot.command(name='mute_until')
        async def mute_until(ctx, date):
            try:
                await ctx.message.delete()
            except discord.errors.Forbidden:
                pass
        
            try:
                until = datetime.date(*[int(x) for x in date.split('/')])
            except Exception as e:
                logger.warning(str(e))
                await ctx.author.send(
                    'Unable to mute you, date format unknown. '
                    'Please provide a date like this: YYYY/MM/DD, '
                    'so for example `!mute_until 2020/01/01`'
                )
                
            user, _ = models.User.objects.get_or_create(
                discord_id=ctx.author.id, 
                defaults={
                    'username': ctx.author.id, 
                    'first_name': ctx.author.display_name, 
                    'last_name': ctx.author.discriminator
                })
            
            user.mute_until = until
            user.save()

            await ctx.author.send(
                f"Thanks, you won't participate in standups until {until}"
            )

        @bot.command(name='newstandup')
        async def newstandup(ctx, standup_type):
            
            try:
                stype = models.StandupType.objects.get(
                    command_name=standup_type
                )
            except models.StandupType.DoesNotExist:
                msg = (
                    'Please provide a valid standup type as the argument '
                    'of this function, your options are:\n\n'
                )
                msg += '\n'.join([
                    f'`{s.command_name}` ({s.name})'
                    for s in models.StandupType.objects.all()
                ])
                await ctx.author.send(msg)
                await ctx.message.delete()
                return 

            if not ctx.author.permissions_in(ctx.channel).manage_messages:
                await ctx.author.send(
                    'Sorry, you have no permission to do this! '
                    'Only users with the permission to manage roles '
                    'for a given channel can do this.'
                )
            else:
                if (
                    models.StandupEvent.objects.create_from_discord(
                        stype, ctx.channel, ctx.author
                    )
                ):
                    await ctx.send(
                        f'{stype.name} initialized for this channel!'
                    )
                else:
                    await ctx.send(
                        f'This channel already has a {stype.name}, '
                        f'no new one was created.'
                    )

            await ctx.message.delete()

        async def interval():
            await asyncio.sleep(10)

            tz = timezone.get_default_timezone()
    
            while True:
                # Repetitive task checks here
                for ev in models.StandupEvent.objects.all():
                    success, to_notify = ev.initiate()
                    if not success:
                        continue
                    for participant in to_notify:
                        did = int(participant.user.discord_id)
                        await bot.wait_until_ready()
                        user = bot.get_user(did)
                        for i in range(5):
                            try:

                                if not participant.read_only:
                                    await user.send(
                                        f'Please answer the questions '
                                        f'for "{participant.standup.event.standup_type.name}" '  # noqa
                                        f'in "{participant.standup.event.channel}" '  # noqa
                                        f'here: {participant.get_form_url()} - Thanks!'  # noqa
                                    )

                                await user.send(
                                    f'You can view your '
                                    f'private standup overview '
                                    f'here: {participant.get_home_url()}'
                                )
                                break
                            except Exception as e:
                                logger.error(
                                    f'Something went wrong while sending form '
                                    f'to the user: {e}'
                                )
                                logger.info(f'Trying to resend ({i})...')
                                await asyncio.sleep(2)

                standups = models.Standup.objects.filter(
                    pinned_message_id__isnull=True,
                    rebuild_message=True,
                    event__standup_type__publish_to_channel=True
                )
                for standup in standups:
                    await standup.send_summary(bot)

                await asyncio.sleep(10)

        try:
            bot.loop.run_until_complete(
                asyncio.gather(bot.start(settings.DISCORD_TOKEN), interval())
            )
        except KeyboardInterrupt:
            bot.loop.run_until_complete(bot.logout())
        finally:
            bot.loop.close()
