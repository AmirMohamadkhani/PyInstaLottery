import instaloader
import pandas as pd
import os
import requests
from bs4 import BeautifulSoup as bs
import shutil

class MyRateController(instaloader.RateController):
    def count_per_sliding_window(self, query_type):
        return 20

class InstaLottery:
    def __init__(self, username, password):
        self.login = self.login_insta(username, password)

    def login_insta(self, username, password):
        #L = instaloader.Instaloader(rate_controller=lambda ctx: MyRateController(ctx))
        L = instaloader.Instaloader()
        if username != "":
            if password == "":
                L.interactive_login(username)
            else:
                L.login(username, password)
        
        return L

    def get_followers_list(self, profile_name):
        followers_list = []
        profile = instaloader.Profile.from_username(self.login.context, profile_name)
        followers = profile.get_followers()
        for follower in followers:
            followers_list.append(follower.username)
        return followers_list


    def fetch_post(self, post_id):
        post = instaloader.Post.from_shortcode(self.login.context, post_id)
        return post
        
    def get_likes_list(self, post):
        likes_list = []
        likes = post.get_likes()
        
        for like in likes:
            likes_list.append(like.username)
        return likes_list

    def get_comment_list(self, post):
        cText = {}
        cCount = {}
        comments = post.get_comments()
        for comment in comments:
            comment_owner = comment.owner.username
            comment_text = comment.text
            if comment_owner in cText:
                cText[comment_owner] += comment_text  + ","
                cCount[comment_owner] = cCount[comment_owner] + 1
            else:
                cText[comment_owner] = comment_text
                cCount[comment_owner] = 1

        return cCount

    def getCommentCount(self, post):

        comments = post.get_comments()
        userList = []
        userComment = []
        for comment in comments:
            if not('@' in comment.text):
                userList.append(comment.owner.username)
                userComment.append(comment.text)

        df = pd.DataFrame()
        df['username'] = userList
        df['text'] = userComment
        result = df.groupby(['username']).size().reset_index(name='commentCount')
        return result

    def getMentionsCount(self, post):
        df = pd.DataFrame(post.get_comments())
        userList = []
        for userProf in df['owner']:
            userList.append(userProf.username)
        df['username'] = userList

        mentionCount = []
        for comment in df['text']:
            words = comment.split(" ")
            mentionCount.append(len([k for k in words if ('@' in k) & (len(k) > 5)]))

        df['mentionCount'] = mentionCount

        return df.groupby(['username']).agg({'mentionCount':'sum'}).reset_index()


    def createOutputFile(self, post, featureDict, minComments):
        finalDF = pd.DataFrame()

        if featureDict["comments"]:
            commentDF = self.getCommentCount(post) 
            finalDF = commentDF            
            finalDF = finalDF.loc[(finalDF.commentCount >= int(minComments))]

        if featureDict["mentions"]:
            mentionDF = self.getMentionsCount(post)
            if finalDF.size > 0:
                finalDF = commentDF.merge(mentionDF, how='outer').fillna(0)
            else:
                finalDF = mentionDF
            finalDF = finalDF.loc[(finalDF.mentionCount > 0)]

        if featureDict["likeit"]:
            finalDF['liked'] = False
            likeDF = self.get_likes_list(post)
            if finalDF.size > 0:
                for user in likeDF:
                    mask = finalDF.username.str.contains(user)
                    column_name = 'liked'
                    finalDF.loc[mask, column_name] = True
            else:
                finalDF = pd.DataFrame(likeDF, columns =['username'])
                finalDF['liked'] = True
                
            finalDF = finalDF.loc[(finalDF['liked'])]

        if featureDict["follower"]:
            finalDF['followed'] = False
            followerDF = self.get_followers_list(post.owner_username)
            if finalDF.size > 0:
                for user in followerDF:
                    mask = finalDF.username.str.contains(user)
                    column_name = 'followed'
                    finalDF.loc[mask, column_name] = True
            else:
                finalDF = pd.DataFrame(followerDF, columns =['username'])
                finalDF['followed'] = True

            finalDF = finalDF.loc[(finalDF['followed'])]


        # first_col = finalDF.pop("username")
        # finalDF.head()
        # finalDF.insert(0, "username", first_col)

        return finalDF

    def deleteWinnersImage(self):
        dir_path = os.path.dirname(os.path.realpath(__file__))
        shutil.rmtree(dir_path + "\\static\\temp_images")
        os.mkdir(dir_path + "\\static\\temp_images")


    def calculateScore(self, userFrame, minComments):
        userFrame['score'] = 1
        for row in range(len(userFrame.index)):
            score = 1
            if 'liked' in userFrame:
                score += 1
            if 'mentionCount' in userFrame:
                score += int(userFrame['mentionCount'].iloc[row])
            if 'followed' in userFrame:
                score += 1
            if 'commentCount' in userFrame:
                score += int((userFrame['commentCount'].iloc[row])/int(minComments))

            mask = userFrame.username.str.contains(userFrame['username'].iloc[row])
            userFrame.loc[mask, 'score'] = score

        userFrame['weight'] = 0
        sum = userFrame['score'].sum()
        for row in range(len(userFrame.index)):            
            mask = userFrame.username.str.contains(userFrame['username'].iloc[row])
            userFrame.loc[mask, 'weight'] = int(userFrame['score'].iloc[row]) / sum

        return userFrame

    def executeLottery(self, userFrame, winnerCount):       

        if (len(userFrame.index) < int(winnerCount)):
            winnerCount = len(userFrame.index)

        
        winnerFrame = userFrame['username'].sample(n = int(winnerCount), weights = userFrame['weight'])

        winnerDict = {}
        for row in winnerFrame:
            self.login.download_profile(row,profile_pic_only=True)
            winnerDict[row] = self.navigate_and_rename(row)
        return winnerDict

    def navigate_and_rename(self,name):
        dir_path = os.path.dirname(os.path.realpath(__file__))
        src = dir_path + "\\" + name                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           
        for item in os.listdir(src):
            s = os.path.join(src, item)
            if s.endswith(".jpg"):
                filePath = os.path.join(dir_path + "\\static\\temp_images", name + ".jpg")
                shutil.copy(s, filePath)  
                shutil.rmtree(dir_path + "\\" + name)   
                return "/static/temp_images/" + name + ".jpg"

        return ""


    def saveDftoExcel(self, dataframe):
        generator = (cell for row in dataframe
                    for cell in row)

        return generator


    def process_tags(self, text):
        tagCount = {}
        for item in text.split():
            if item.startswith('@'):
                print(item)




