import asyncio
import discord
from discord.ext import commands
import mcstatus
import json

SERVER_IP = ''
USER_DATA_FILE = 'users.json'
TOKEN = ''

bug = commands.Bot(command_prefix='$')

user_data = {}

# loads in from USER_DATA_FILE
def load_user_data():
    global user_data
    try:
        with open(USER_DATA_FILE, 'r') as f:          
            user_data = json.load(f)
    except (FileNotFoundError, json.decoder.JSONDecodeError):
        # if there is an error loading the json, user_data stays as an empty dict
        return


# saves to USER_DATA_FILE
def save_user_data():
    with open(USER_DATA_FILE, 'w') as f:
        json.dump(user_data, f, indent=2)


# returns minecraft username by looking up discord username or id
def get_mcuser(name):
    for u in user_data:
        if (name == user_data[u]['discord_name']):
            return u
        elif (name == f'<@!{user_data[u]["discord_id"]}>'):
            user = bug.get_user(user_data[u]['discord_id'])
            return u


# a class with query data from the server
class ServerData:
    def update(self):
        mc_server = mcstatus.MinecraftServer.lookup(SERVER_IP)

        # attempts to query server
        # flags success as False if query fails
        try: 
            stat = mc_server.status()
            self.online  = stat.players.online
            self.max     = stat.players.max
            self.players = {}
            self.success = True

            if stat.players.sample:
                for p in stat.players.sample:
                    self.players[p.name] = p.id

        except (ConnectionRefusedError, OSError):
            self.success = False

query = ServerData()


# runs on bot startup
# loads data and begins tasks
@bug.event
async def on_ready():
    print('Connected to {0}'.format(' '.join([f'[{x.name}]' for x in bug.guilds])))

    load_user_data()

    bug.loop.create_task(update_player_count())
    bug.loop.create_task(update_player_data())


# updates the status of the bot, displaying the number of users on the server
async def update_player_count():
    await bug.wait_until_ready()

    while True:
        query.update()

        # sets status text based on whether server is up or not
        if query.success:
            text = f'the server [{query.online}/{query.max}]'
        else:
            text = 'the server is offline'
        
        await bug.change_presence(
            activity=discord.Activity(
            type=discord.ActivityType.watching, 
            name=text))

        await asyncio.sleep(5)


# records how long players are on the server in minutes
async def update_player_data():
    while True:
        if query.success:
            for p in query.players.items():
                name, id = p

                # adds new entry for unknown users
                if name not in user_data:
                    user_data[name] = {'time': 1, 'uuid': id, 'discord_name': '', 'discord_id': ''}
                # adds one minute to total time for existing users
                else:
                    user_data[name]['time'] += 1
                    
            save_user_data()
        
        await asyncio.sleep(60)


# displays online users
@bug.command(
    help='Displays the number of users on the server and their usernames.',
    brief='Shows people online')
async def online(ctx):
    query.update()
    
    # sends different messages based on whether server is up, and how many players are online
    if query.success:
        if query.online == 0:
            await ctx.send('No one is currently online. :cry:')
        elif query.online == 1:
            await ctx.send('1 person is currently online:\n> {0}'.format("\n> ".join(query.players.keys())))
        else:
            await ctx.send('{0} people are currently online:\n> {1}'.format(query.online, "\n> ".join(query.players.keys())))
    else:
        await ctx.send('The server is offline. :sob:')


# sends a message shaming the user with the highest playtime
@bug.command(
    help='Just see what happens...'
)
async def shame(ctx):
    time_highest = 0
    user_highest = ''

    # iterates through user data and finds highest playtime
    for u in user_data:
        user = user_data[u]
        if user['time'] > time_highest:
            time_highest = user['time']
            user_highest = u

    if user_data[user_highest]['discord_id']:
        await ctx.send(f"<@!{user_data[user_highest]['discord_id']}> has played for {time_highest//60} hours! Shameful!")
    else:
        await ctx.send(f"{user_highest} has played for {time_highest//60} hours, and hasn't verified their account! Even more shameful!")


# displays playtime of yourself or another user
@bug.command(
    help='Displays your total playtime, or if you add a username afterwards, that of another player. (Must be verified).',
    brief='Shows playtime',
    usage='(discord username) (optional)')
async def playtime(ctx):
    id = ctx.author.id
    words = ctx.message.content.split()

    # retrieves time from a user and formats it
    def get_time(user):
        minutes = user_data[user]["time"]
        if minutes > 60:
            hours = minutes // 60
            return f'{hours} hours'
        else:
            return f'{minutes} minutes'

    # checks for own playtime
    if (len(words) == 1):
        for u in user_data:
            if (id == user_data[u]['discord_id']):
                await ctx.send(f'You have played for {get_time(u)}!')
                return
        await ctx.send('Please verify your account! ($verify username)')

    # checks for requested user's playtime
    elif (len(words) > 1):
        name = ' '.join(words[1:])
        user = get_mcuser(name)
        
        if user:
            await ctx.send(f'{name} has played for {get_time(user)}!')
        else:
            await ctx.send(f"{name} doesn't exist, or needs to verify their account!")


# ping command checks if bot is alive and provides basic contextual information
@bug.command(
    help='Checks if bot is alive')
async def ping(ctx):
    await ctx.send(f'pong :wink: (from user {ctx.author.id} on server {ctx.guild.id if ctx.guild else None} channel {ctx.channel.id})')


# displays a user's minecraft name
@bug.command(
    help='Gives the Minecraft username of a discord user. (Must be verified).',
    brief='Gets Minecraft username',
    usage='(discord username)')
async def whois(ctx):
    words = ctx.message.content.split()

    # checking input format
    if (len(words) > 1):
        name = ' '.join(words[1:])
    else:
        await ctx.send('Please enter a discord username.')
        return

    user = get_mcuser(name)
    
    if user:
        await ctx.send(f'{name} is {user}')
    else:
        await ctx.send("I don't know :pleading_face:")


# links a user's discord account to their minecraft username
@bug.command(
    help='Enter your Minecraft username and follow the instructions to verify your account.',
    brief='Verifies account',
    usage='(minecraft username)')
async def verify(ctx):
    words = ctx.message.content.split()

    if (len(words) == 2):
        name = words[1]
    else:
        await ctx.send('Please enter your minecraft username.')
        return

    if name in user_data: 
        if user_data[name]['discord_name']:
            await ctx.send('Your account has already been verified!')
            return
    else:
        await ctx.send("I don't recognize that username. (Make sure you've joined the server before!)")
        return

    msg = await ctx.send(
        '''In order to verify your account: 
        1. Make sure you are disconnected
        2. Press the thumbs up!
        3. Log onto the server and wait a few seconds
        4. Log off again''')
    await msg.add_reaction('👍')

    # starts verifier if user reacts before timeout
    def check(reaction, user):
        return user == ctx.author and str(reaction.emoji) == '👍'

    # user has a minute to start the process
    try:
        reaction, user = await bug.wait_for('reaction_add', timeout=60.0, check=check)    
    # failure (timeout)
    except asyncio.TimeoutError:
        pass
    # success (schedules verifier task)
    else:
        await msg.remove_reaction('👍', bug.user)
        bug.loop.create_task(verifier(ctx, name))


# completes actual verification process
async def verifier(ctx, name):
    def online():
        return name in query.players.keys() 

    count = 1
    started_off = False
    connected = False
    success = False

    while True:
        query.update()

        if not query.success:
            await ctx.send('The server is offline. :sob:')
            return
        
        # checks if user disconnects
        if (connected):
            if not online():
                success = True
                break

        # checks if user connects
        if (started_off):
            if online():
                connected = True

        # checks if user starts offline
        if (online() and count == 1):
            break
        else:
            started_off = True

        # process times out after 20 seconds
        if (count > 20):
            break
        
        count += 1
        await asyncio.sleep(1)

    # if process completes, discord and minecraft names are linked
    if (success):
        await ctx.send('Verification successful!')
        user_data[name]['discord_name'] = ctx.author.name
        user_data[name]['discord_id'] = ctx.author.id
        save_user_data()
    # error messages for different user errors
    else:
        if not started_off:
            await ctx.send('Verification failed. (Make sure to start disconnected!)')
        elif not connected:
            await ctx.send('Verification failed. (You never logged on!)')
        elif not success:
            await ctx.send('Verification failed. (Make sure to disconnect after a few seconds!)')


bug.run(TOKEN)