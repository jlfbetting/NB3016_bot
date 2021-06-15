#!/usr/bin/env python
# coding: utf-8

# In[1]:


import boto3
import re
import os
import time
import pytz
import dill
import threading
from datetime import datetime, timedelta
import discord
import numpy as np
import nest_asyncio
from discord.utils import get
from credentials import *

client = boto3.client(
    'ec2',
    aws_access_key_id=AWS_ACCCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
)
ec2 = boto3.resource('ec2')


def instance_by_name(name):
    if name.startswith("i-"):
        return name
    custom_filter = [{
    'Name':'tag:Name', 
    'Values': [name]}]
    response = client.describe_instances(Filters=custom_filter)
    try:
        ID = response['Reservations'][0]['Instances'][0]['InstanceId']
    except:
        return False
    return ID 



class InstanceMonitor:                               ## CLASS TO MONITOR INSTANCE
    def __init__(self,ID,weeklyBudget=18,assignedUser=''):           # Constructor
        self.ID = ID
        self.assignedUser = assignedUser
        self.weeklyBudget = weeklyBudget # in hours
        self.firstDay = 0 # Monday is the first day
        self.listOfStateChanges = [];
        if os.path.exists('./' + ID + '.dill'):                    # load history from file if it exists
            with open(self.ID + '.dill', "rb") as dill_file:
                self.listOfStateChanges = dill.load(dill_file)
        self.running = True;                                       # the monitor should run continuously
        self.monitor = threading.Thread(target=self.monitorEvery, args=())   # creating monitor thread
        self.monitor.start()                                       # starting up the monitor thread
    def monitorEvery(self,interval=5):
        old_runCode = -1
        while self.running:
            myState = client.describe_instances(InstanceIds=[self.ID])
            self.runCode = myState['Reservations'][0]['Instances'][0]['State']['Code']   # get the run code
            if old_runCode == -1:
                old_runCode = self.runCode;                                              # this only applies in 1st iteration
            if old_runCode == 16 and (self.calculateUse() > (self.weeklyBudget*3600)):   # if running, but out of budget, then stop
                self.stop();
            if self.runCode != old_runCode:                                              # in case of state change
                if self.runCode == 16: # starting event                         # This means, the instance has just started
                    self.listOfStateChanges.append((1,time.time()))
                elif old_runCode == 16: # stopping event:                       # This means, the instance has just stopped
                    self.listOfStateChanges.append((0,time.time()))
                with open(self.ID + '.dill', "wb") as dill_file:                # Save history to file
                    dill.dump(self.listOfStateChanges,dill_file)
                old_runCode = self.runCode;                                     # update old runcode
            time.sleep(interval)
    def start(self):
        if self.calculateUse() > (self.weeklyBudget*3600):                      # can't start if out of budget
            return -1
        try:
            client.start_instances(InstanceIds=[self.ID])
            return 0;
        except:
            return 1;
    def stop(self):
        try:
            client.stop_instances(InstanceIds=[self.ID])
            return 0;
        except:
            return 1;
    def lastResetDate(self):                # Find the last time that the budget was reset
        stamp = time.time()
        weekstartTime = datetime.fromtimestamp(stamp)
        weekDay = weekstartTime.weekday()
        while weekDay != self.firstDay:
            weekstartTime -= timedelta(days=1)
            weekDay = weekstartTime.weekday()
        weekstartTime = weekstartTime.replace(hour=0, minute=0,                                               second=0, microsecond=0).timestamp()
        return weekstartTime
    def calculateUse(self,formatted=False):                 # Calculate total use this week in seconds
        weekStartTime = self.lastResetDate()
        myChanges = [x for x in self.listOfStateChanges if x[1] > weekStartTime]
        if len(myChanges) == 0:
            if self.runCode == 16:
                myUse = time.time() - weekStartTime;
                used_hours = np.floor(myUse/3600);
                used_mins = np.ceil((myUse-used_hours*3600)/60);
                formattedUse = '{:d}:{:02d}'.format(int(used_hours),int(used_mins))
            else:
                myUse = 0;
                formattedUse = '0:00';
        else:
            if myChanges[0][0] == 0:
                myChanges.insert((1,weekStartTime),0)
            if myChanges[-1][0] == 1:
                myChanges.append((0,time.time()))
            myUse = sum([x[1] for x in myChanges if x[0] == 0]) - sum([x[1] for x in myChanges if x[0] == 1])
            used_hours = np.floor(myUse/3600);
            used_mins = np.ceil((myUse-used_hours*3600)/60);
            formattedUse = '{:d}:{:02d}'.format(int(used_hours),int(used_mins))
        if formatted:
            return myUse, formattedUse
        else:
            return myUse
    def getIP(self):
        try:
            myIp = client.describe_instances(InstanceIds=[self.ID])['Reservations'][0]['Instances'][0]['NetworkInterfaces'][0]['Association']['PublicIp'];
            return myIp;
        except:
            return -1;
    def instanceState(self):
        myState = client.describe_instances(InstanceIds=[self.ID])
        return myState['Reservations'][0]['Instances'][0]['State']['Name']   # get the run code
    def delete(self):                            # Delete monitor
        self.running = False;
        self.monitor.join()
        print("stopped successfully!")
    def __del__(self):                           # destructor
        self.delete()


if os.path.exists('myList.dill'):
    with open('myList.dill', "rb") as dill_file:
        myList = dill.load(dill_file)
else:
    myList = {}
if os.path.exists('myUserIDs.dill'):
    with open('myUserIDs.dill', "rb") as dill_file:
        myUserIDs = dill.load(dill_file);
else:
    myUserIDs = {}
if os.path.exists('myAssignments.dill'):
    with open('myAssignments.dill', "rb") as dill_file:
        myAssignments = dill.load(dill_file);
else:
    myAssignments = {}


intents = discord.Intents.default()
intents.members = True
dclient = discord.Client(intents=intents)


def save_all_lists():
    with open('myList.dill', "wb") as dill_file:
        dill.dump(myList,dill_file);
    with open('myUserIDs.dill', "wb") as dill_file:
        dill.dump(myUserIDs,dill_file);
    with open('myAssignments.dill', "wb") as dill_file:
        dill.dump(myAssignments,dill_file);

@dclient.event
async def on_ready():
    print('We have logged in as {0.user}'.format(dclient))


# In[51]:


@dclient.event
async def on_message(message):
    myMember = get(dclient.guilds[0].members, id=message.author.id)
    if not myMember:
        print("Not a member of the guild!")
        return;
    if message.author == dclient.user:
        return;
    if get(myMember.roles, name="TA") or get(myMember.roles, name="Professor"):
        isAdmin = True;
        print("this is a TA or Professor")
    else:
        isAdmin = False;
    if message.content == '$hello':
        userName = message.author.name.split("#")[0]

        if userName not in myList.keys():
            await message.channel.send('The administrator has not assigned an instance to you! Please message them')
            return;
        if message.author.id in myAssignments.keys():
            await message.channel.send('You already have an instance assigned to you!')
            return;
        instance_name = myList[userName];
        myID = instance_by_name(instance_name)
        if myID == False:
            await message.channel.send('Error assigning instance. Please contact the administrator')
            return;
        myUserIDs[userName] = message.author.id
        myAssignments[message.author.id] = InstanceMonitor(myID,assignedUser=message.author.id)
        myIP = myAssignments[message.author.id].getIP()
        if myIP == -1:
            await message.channel.send('Error assigning IP address. Please contact the administrator')
            return;
        await message.channel.send('Congratulations! Instance with IP address {} was assigned to you!'.format(myIP))
        await message.channel.send('You can use the following commands with this bot:\n $info : Get information about your instance and budget \n $start : Start your instance \n $stop : Stop your instance')
        save_all_lists()
    if message.content == '$info':
        try:
            instance = myAssignments[message.author.id];
        except:
            message.channel.send("We couldn't check your instance state. Do you have an instance assigned to you?")
            return
        await message.channel.send('Instance IP: {}'.format(instance.getIP()))
        await message.channel.send('Instance state: {}'.format(instance.instanceState()))
        weekly_hours = np.floor(instance.weeklyBudget)
        weekly_minutes = np.floor((instance.weeklyBudget-weekly_hours)*60)
        await message.channel.send('Budget: {:d}:{:02d}'.format(int(weekly_hours),int(weekly_minutes)));
        used_sec, formattedUse = instance.calculateUse(formatted=True)
        used_hours = np.floor(used_sec/3600);
        used_mins = np.ceil((used_sec-used_hours*3600)/60);
        await message.channel.send('Used time: {}'.format(formattedUse))
        left_sec = instance.weeklyBudget*3600-used_sec;
        left_hours = np.floor(left_sec/3600);
        left_mins = np.floor((left_sec-left_hours*3600)/60);
        await message.channel.send('Time left this week: {:d}:{:02d}'.format(int(left_hours),int(left_mins)))
    if message.content == '$start':
        try:
            instance = myAssignments[message.author.id];
        except:
            await message.channel.send("We couldn't start your instance. Do you have an instance assigned to you?")
            return
        returnVal = instance.start();
        if returnVal == 0:
            await message.channel.send("Instance is starting! You should be able to connect within a few minutes.\nDon't forget to connect to eduVPN.")
        elif returnVal == -1:
            await message.channel.send("Couldn't start instance, as you're out of budget!")            
        else:
            await message.channel.send("Couldn't start instance! Maybe it is already starting, or busy shutting down?")
     #   print(returnVal)
    if message.content == '$stop':
        try:
            instance = myAssignments[message.author.id];
        except:
            await message.channel.send("We couldn't stop your instance. Do you have an instance assigned to you?")
            return
        returnVal = instance.stop();
        if returnVal == 0:
            await message.channel.send("Instance is stopping!")      
        else:
            await message.channel.send("Couldn't stop instance! Maybe it is busy starting or shutting down?")
    if isAdmin:
        if message.content == '$admin':
            await message.channel.send("These are your admin commands:\n" +                                        " $list - List all the usernames with assigned instance IDs.\n" +                                        " $budgets - List all the usernames with available / used budgets.\n" +                                        " $remove:<USER> - Remove user from the list.\n" +                                        " $budget:<USER>:<HOURS> - Adjust the budget of a user.\n" +                                        " $assign:<USER>:<INSTANCE> - assign instance (name or ID, avoid ':') to user\n" +                                        " For more power, check the EC2 Dashboard");
        if message.content == '$list':
            txtMessage = 'USER :: INSTANCE ID :: CLAIMED\n';
            for user in myList.keys():
                myID = instance_by_name(myList[user])
                if user in myUserIDs.keys():
                    claimed = "YES"
                else:
                    claimed = "NO"
                txtMessage += user + " :: " + myID + " :: " + claimed + "\n"
            await message.channel.send(txtMessage)
        if  message.content == '$budgets':
            txtMessage = 'USER :: USED BUDGET :: TOTAL BUDGET\n';
            for user in myList.keys():
                if user in myUserIDs.keys():
                    instance = myAssignments[myUserIDs[user]]
                    _, used = instance.calculateUse(formatted=True)
                    txtMessage += user + " :: " + used + " :: " + str(int(instance.weeklyBudget)) + ":00\n"
            await message.channel.send(txtMessage)
        if  message.content.startswith('$remove:'):
            try:
                user = message.content.replace('$remove:','')
                if user in myUserIDs.keys():
                    myAssignments[myUserIDs[user]].delete();
                    myAssignments[myUserIDs[user]]
                    del myAssignments[myUserIDs[user]]
                if user in myList.keys():
                    del myList[user]
            except:
                await message.channel.send("Couldn't remove user! Please check your statement")
                return
            await message.channel.send("User {} was removed!".format(user))
            save_all_lists()
        if  message.content.startswith('$assign:'):
            try:
                user_instance = message.content.replace('$assign:','')
                user_instance = user_instance.split(':')
                if len(user_instance) > 2:
                    user = ':'.join(user_instance[:-1])
                else:
                    user = user_instance[0]
                instanceName = user_instance[-1]
                print(instanceName)
                instanceId = instance_by_name(instanceName)
                print(instanceId)
            except:
                await message.channel.send("Couldn't assign instance! Please check your statement")
                return
            myList[user] = instanceId
            await message.channel.send("Instance ID {} assigned to user {}".format(instanceId, user))
            save_all_lists()
        if  message.content.startswith('$budget:'):
            try:
                user_instance = message.content.replace('$budget:','')
                user_instance = user_instance.split(':')
                if len(user_instance) > 2:
                    user = ':'.join(user_instance[:-1])
                else:
                    user = user_instance[0]
                budget = float(user_instance[-1])
            except:
                await message.channel.send("Couldn't assign budget! Please check your statement")
                return
            myAssignments[myUserIDs[user]].weeklyBudget = budget
            await message.channel.send("Budget of user {} adjusted to {}".format(user,budget))
            save_all_lists()


# In[ ]:


nest_asyncio.apply()
dclient.run(DISCORD_BOT_TOKEN)


# In[ ]:




