# PS3-Rich-Presence-Plus
Discord Rich Presence script for PS3 consoles on HFW&HEN or CFW.

Display what game you are playing on PS3 via your PC!
 
# Main Additions
* Changes networkscan for concurrent.futures dependences.
* Adds WebMAN to search for cover images.
* Adds Regex to change game titles that end on game versions (Ex: "1.00")
* Adds show_xmb to the config file to hide the status while you're on the PS3 menu.

## Display Example
<table>
	<tr>
		<td>XMB</td>
		<td> <img src="https://github.com/zorua98741/PS3-Rich-Presence-for-Discord/blob/main/img/xmb.png?raw=true"> </td>
	</tr>
	<tr>
		<td>PS3</td>
		<td> <img src="https://github.com/zorua98741/PS3-Rich-Presence-for-Discord/blob/main/img/ps3.png?raw=true"> </td>
	</tr>
	<tr>
		<td>PS1/2</td>
		<td> <img src="https://github.com/zorua98741/PS3-Rich-Presence-for-Discord/blob/main/img/retro.png?raw=true"> </td>
	</tr>
</table>


## Usage

### Requirements
* PS3 with either HFW&HEN, or CFW installed
* PS3 with [webmanMOD](https://github.com/aldostools/webMAN-MOD/releases) installed 
* PS3 and PC on the same network/internet connection
* Discord installed and open on the PC running the script
* A Python 3.9 interpreter installed on the PC if you do not wish to use the executable file
* __requirements.txt Python dependences installed.__

### Windows
* Clone the repo
* Launch PS3RPD.pyw

### Optional (Start at Boot)
* If you want it to start at boot, create a shortcut of the PS3RPD.pyw, 
* Press Win + R and paste "shell:startup"
* Paste the shortcut in that folder.


## Limitations
* __A PC must be used to display presence, there is no way to install and use this script solely on the PS3__
* The script relies on webmanMOD, and a major change to it will break this script, please message me about updated versions of webman so that i can test the script with them
* PSX and PS2 game name depends on the name of the file
* PSX and PS2 game detection will **not** work on PSN .pkg versions because webman cannot show those games as mounted/playing.
* PS2 ISO game detection can be inconsistent, varying on degree of consistency by the value of "Refresh time."


## Additional Information

### GameTDB + Webman
This script uses images provided by [GameTDB](https://www.gametdb.com/) and [Aldostools (WebMAN)](https://raw.githubusercontent.com/aldostools/Resources). If you are able, consider supporting them.

### External config file
PS3RPD makes use of an external config file to persistently store a few variables, on creation, the default values will be:
* Your PS3's IP address 	(If you don't know it will search it automatically until find a PS3 with enabled HEN.)
* zorua98741 Discord developer application's ID 		(where the script will send presence data to)
* A refresh time of 45 seconds 				 (how often will get new data)
* To show the PS3's temperature
* To show Rich Prescense if you're on XMB
* A hibernate time of 10 seconds (waiting time to search for IP's again)
