#!/usr/bin/env python

import base64
import datetime
import os
import sys
import traceback

sys.path.insert(0, "%s/../../util/python" % os.path.dirname(os.path.realpath(__file__)))
import Cons
import Util

import GetIPs

_fo_log = None


def _Log(msg):
	fn = "/var/log/acorn/ec2-init.log"
	global _fo_log
	if _fo_log == None:
		_fo_log = open(fn, "a")
	_fo_log.write("%s: %s\n" % (datetime.datetime.now().strftime("%y%m%d-%H%M%S"), msg))
	_fo_log.flush()


def _RunSubp(cmd, shell = False):
	_Log(cmd)
	r = Util.RunSubp(cmd, shell = shell, print_cmd = False, print_result = False)
	if len(r.strip()) > 0:
		_Log(Util.Indent(r, 2))


_region = None

def _SetHostname(job_id):
	az = Util.RunSubp("curl -s http://169.254.169.254/latest/meta-data/placement/availability-zone", print_cmd = False, print_result = False)
	global _region
	_region = az[:-1]

	# Hostname consists of availability zone name and launch req datetime
	hn = "%s-%s" % (az, _tags["acorn_exp_param"], job_id)

	# http://askubuntu.com/questions/9540/how-do-i-change-the-computer-name
	cmd = "sudo sh -c 'echo \"%s\" > /etc/hostname'" % hn
	Util.RunSubp(cmd, shell=True)
	cmd = "sudo sed -i '/^127.0.0.1 localhost.*/c\\127.0.0.1 localhost %s' /etc/hosts" % hn
	Util.RunSubp(cmd, shell=True)
	cmd = "sudo service hostname restart"
	Util.RunSubp(cmd)


def _SyncTime():
	# Sync time. Important for Cassandra.
	# http://askubuntu.com/questions/254826/how-to-force-a-clock-update-using-ntp
	_Log("Synching time ...")
	_RunSubp("sudo service ntp stop")

	# Fails with a rc 1 in the init script. Mask with true for now.
	_RunSubp("sudo /usr/sbin/ntpd -gq || true", shell = True)

	_RunSubp("sudo service ntp start")


def _InstallPkgs():
	_RunSubp("sudo apt-get update && sudo apt-get install -y pssh dstat", shell = True)


def _MountAndFormatLocalSSDs():
	# Make sure we are using the known machine types
	inst_type = Util.RunSubp("curl -s http://169.254.169.254/latest/meta-data/instance-type", print_cmd = False, print_result = False)
	if not inst_type.startswith("c3."):
		raise RuntimeError("Unexpected instance type %s" % inst_type)

	ssds = ["ssd0", "ssd1"]
	devs = ["xvdb", "xvdc"]

	for i in range(2):
		_Log("Setting up Local %s ..." % ssds[i])
		_RunSubp("sudo umount /dev/%s || true" % devs[i], shell=True)
		_RunSubp("sudo mkdir -p /mnt/local-%s" % ssds[i])

		# Instance store volumes come TRIMmed when they are allocated. Without
		# nodiscard, it takes about 80 secs for a 800GB SSD.
		_RunSubp("sudo mkfs.ext4 -m 0 -E nodiscard -L local-%s /dev/%s" % (ssds[i], devs[i]), shell=True)

		# -o discard for TRIM
		_RunSubp("sudo mount -t ext4 -o discard /dev/%s /mnt/local-%s" % (devs[i], ssds[i]), shell=True)
		_RunSubp("sudo chown -R ubuntu /mnt/local-%s" % ssds[i], shell=True)


def _CloneAcornSrcAndBuild():
	_RunSubp("mkdir -p /mnt/local-ssd0/work")
	_RunSubp("rm -rf /mnt/local-ssd0/work/acorn")
	_RunSubp("git clone https://github.com/hobinyoon/apache-cassandra-3.0.5-src.git /mnt/local-ssd0/work/apache-cassandra-3.0.5-src")
	_RunSubp("rm -rf /home/ubuntu/work/acorn")
	_RunSubp("ln -s /mnt/local-ssd0/work/apache-cassandra-3.0.5-src /home/ubuntu/work/acorn")
	# Note: report progress. clone done.

	# http://stackoverflow.com/questions/26067350/unmappable-character-for-encoding-ascii-but-my-files-are-in-utf-8
	_RunSubp("cd /home/ubuntu/work/acorn && (JAVA_TOOL_OPTIONS=-Dfile.encoding=UTF8 ant)", shell = True)
	# Note: report progress. build done.


def _EditCassConf():
	_Log("Getting IP addrs of all running instances of tags %s ..." % _tags)
	ips = GetIPs.GetByTags(_tags)
	_Log(ips)

	fn_cass_yaml = "/home/ubuntu/work/acorn/conf/cassandra.yaml"
	_Log("Editing %s ..." % fn_cass_yaml)

	cass_cluster_name = _tags["cass_cluster_name"]
	# http://stackoverflow.com/questions/7517632/how-do-i-escape-double-and-single-quotes-in-sed-bash
	_RunSubp("sed -i 's/^cluster_name: .*/cluster_name: '\"'\"'%s'\"'\"'/g' %s"
			% (cass_cluster_name, fn_cass_yaml)
			, shell = True)

	cmd = "sed -i 's/" \
			"^          - seeds: .*" \
			"/          - seeds: \"%s\"" \
			"/g' %s" % (",".join(ips), fn_cass_yaml)
	_RunSubp(cmd, shell = True)

	cmd = "sed -i 's/" \
			"^listen_address: localhost" \
			"/#listen_address: localhost" \
			"/g' %s" % fn_cass_yaml
	_RunSubp(cmd, shell = True)

	cmd = "sed -i 's/" \
			"^# listen_interface: eth0" \
			"/listen_interface: eth0" \
			"/g' %s" % fn_cass_yaml
	_RunSubp(cmd, shell = True)

	# sed doesn't support "?"
	#   http://stackoverflow.com/questions/4348166/using-with-sed
	cmd = "sed -i 's/" \
			"^\(# \|\)broadcast_address: .*" \
			"/broadcast_address: %s" \
			"/g' %s" % (GetIPs.GetMyPubIp(), fn_cass_yaml)
	_RunSubp(cmd, shell = True)

	cmd = "sed -i 's/" \
			"^rpc_address: localhost" \
			"/#rpc_address: localhost" \
			"/g' %s" % fn_cass_yaml
	_RunSubp(cmd, shell = True)

	cmd = "sed -i 's/" \
			"^# rpc_interface: eth1" \
			"/rpc_interface: eth0" \
			"/g' %s" % fn_cass_yaml
	_RunSubp(cmd, shell = True)

	cmd = "sed -i 's/" \
			"^\(# \|\)broadcast_rpc_address: .*" \
			"/broadcast_rpc_address: %s" \
			"/g' %s" % (GetIPs.GetMyPubIp(), fn_cass_yaml)
	_RunSubp(cmd, shell = True)

	cmd = "sed -i 's/" \
			"^endpoint_snitch:.*" \
			"/endpoint_snitch: Ec2MultiRegionSnitch" \
			"/g' %s" % fn_cass_yaml
	_RunSubp(cmd, shell = True)

	# Edit parameters requested from tags
	for k, v in _tags.iteritems():
		if k.startswith("acorn_options."):
			#              01234567890123
			k1 = k[14:]
			cmd = "sed -i 's/" \
					"^    %s:.*" \
					"/%s: %s" \
					"/g' %s" % (k1, k1, v, fn_cass_yaml)
			_RunSubp(cmd, shell = True)


def _EditYoutubeClientConf():
	fn = "/home/ubuntu/work/acorn/acorn/clients/youtube/acorn-youtube.yaml"
	_Log("Editing %s ..." % fn)
	for k, v in _tags.iteritems():
		if k.startswith("acorn-youtube."):
			#              01234567890123
			k1 = k[14:]
			cmd = "sed -i 's/" \
					"^%s:.*" \
					"/%s: %s" \
					"/g' %s" % (k1, k1, v, fn)
			_RunSubp(cmd, shell = True)


def _RunCass():
	_Log("Running Cassandra ...")
	_RunSubp("rm -rf ~/work/acorn/data")
	_RunSubp("/home/ubuntu/work/acorn/bin/cassandra")


def _WaitUntilYouSeeAllCassNodes():
	_Log("Wait until you see all Cassandra nodes ...")
	# Keep checking until you see all nodes are up -- "UN" status.
	while True:
		# Get all IPs with the tags. Hope every node sees all other nodes by this
		# time.
		ips = GetIPs.GetByTags(_tags)
		num_nodes = _RunSubp("/home/ubuntu/work/acorn/bin/nodetool status | grep \"^UN \" | wc -l", shell = True)
		if num_nodes == len(ips):
			break
		time.sleep(2)


def _RunYoutubeClient():
	# Start the experiment from the master (or the leader) node.
	if _region != "us-east-1":
		return
	cmd = "%s/work/acorn/acorn/clients/youtube/run-youtube-cluster.py" % os.path.expanduser('~')
	_RunSubp(cmd)


def _DeqJobReqMsgEnqJobDoneMsg():
	if _region != "us-east-1":
		return

	sqs_url_jr_key = "sqs_url_jr"
	if sqs_url_jr_key not in _tags:
		raise RuntimeError("No %s in tags" % sqs_url_jr_key)
	sqs_url_jr = base64.b64decode(_tags[sqs_url_jr_key])

	sqs_msg_receipt_handle_key_0 = "sqs_message_receipt_handle_0"
	if sqs_msg_receipt_handle_key_0 not in _tags:
		raise RuntimeError("No %s in tags" % sqs_msg_receipt_handle_key_0)
	sqs_msg_receipt_handle_key_1 = "sqs_message_receipt_handle_1"
	if sqs_msg_receipt_handle_key_1 not in _tags:
		raise RuntimeError("No %s in tags" % sqs_msg_receipt_handle_key_1)

	sqs_msg_jr_receipt_handle = _tags[sqs_msg_receipt_handle_key_0] + _tags[sqs_msg_receipt_handle_key_1]

	_DeqJobReqMsg(sqs_url_jr, sqs_msg_jr_receipt_handle)
	_EnqJobdoneMsg(job_id)


_sqs_region = "us-east-1"
_bc = None

def _DeqJobReqMsg(sqs_url_jr, sqs_msg_jr_receipt_handle):
	# Delete the request message from the request queue. Should be done here. The
	# controller node, which launches a cluster, doesn't know when an experiment
	# is done.

	_Log("Deleting the job request message: url: %s, receipt_handle: %s" % (sqs_url_jr, sqs_msg_jr_receipt_handle))
	global _bc
	_bc = boto3.client("sqs", region_name = _sqs_region)
	response = _bc.delete_message(
			QueueUrl = sqs_url_jr,
			ReceiptHandle = sqs_msg_jr_receipt_handle
			)
	_Log(pprint.pformat(response, indent=2))


def _EnqJobdoneMsg():
	_Log("Posting a job completion message ...")

	# Post a "job done" message to the job completed queue, so that the
	# controller node can shutdown the cluster.

	q = _GetJcQ()
	_EnqJcMsg(q, attrs):


q_name_jc = "acorn-jobs-completed"
_sqs = None

# Get the queue. Create one if not exists.
def _GetJcQ():
	global _sqs
	_sqs = boto3.resource("sqs", region_name = _sqs_region)

	_Log("Getting the job completion queue ..."):
	try:
		queue = _sqs.get_queue_by_name(
				QueueName = q_name_jc,
				# QueueOwnerAWSAccountId='string'
				)
		#Cons.P(pprint.pformat(vars(queue), indent=2))
		#{ '_url': 'https://queue.amazonaws.com/998754746880/acorn-exps',
		#		  'meta': ResourceMeta('sqs', identifiers=[u'url'])}
		return queue
	except botocore.exceptions.ClientError as e:
		#Cons.P(pprint.pformat(e, indent=2))
		#Cons.P(pprint.pformat(vars(e), indent=2))
		if e.response["Error"]["Code"] == "AWS.SimpleQueueService.NonExistentQueue":
			pass
		else:
			raise e

	Cons.P("The queue doesn't exists. Creating one ...")
	response = _bc.create_queue(QueueName = q_name_jc)
	# Default message retention period is 4 days.

	return sqs.get_queue_by_name(QueueName = q_name_jc)


msg_body_jc = "acorn-job-completion"

def _EnqJcMsg(q, attrs):
	with Cons.MT("Enq a message ..."):
		msg_attrs = {}
		for k, v in attrs.iteritems():
			msg_attrs[k] = {"StringValue": v, "DataType": "String"}
		q.send_message(MessageBody=msg_body_jc, MessageAttributes={msg_attrs})


def _CacheEbsDataFileIntoMemory():
	_RunSubp("/usr/local/bin/vmtouch -t /home/ubuntu/work/acorn-data/150812-143151-tweets-5667779")


_tags = {}

def main(argv):
	try:
		# This script is run under the user 'ubuntu'.

		if len(argv) != 3:
			raise RuntimeError("Unexpected argv %s" % argv)
		job_id = argv[1]
		tags_str = argv[2]

		global _tags
		_tags = {}
		for kv in tags_str.split(","):
			t = kv.split(":")
			if len(t) != 2:
				raise RuntimeError("Unexpected kv=[%s]" % kv)
			_tags[t[0]] = t[1]

		# Loading the Youtube data file form EBS takes long, like up to 5 mins, and
		# could make a big difference among nodes in different regions, which
		# varies the start times of Youtube clients in different regions.
		t = threading.Thread(target=_CacheEbsDataFileIntoMemory)
		# So that it can (abruptly) terminate on SIGINT
		t.daemon = True
		t.start()

		_SetHostname(job_id)
		_SyncTime()
		_InstallPkgs()
		_MountAndFormatLocalSSDs()
		_CloneAcornSrcAndBuild()
		_EditCassConf()
		_EditYoutubeClientConf()
		_RunCass()

		t.join()

		_WaitUntilYouSeeAllCassNodes()
		_RunYoutubeClient()
		_DeqJobReqMsgEnqJobDoneMsg()
	except Exception as e:
		msg = "Exception: %s\n%s" % (e, traceback.format_exc())
		_Log(msg)
		Cons.P(msg)


if __name__ == "__main__":
	sys.exit(main(sys.argv))
