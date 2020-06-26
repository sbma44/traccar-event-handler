import boto3
from troposphere import Ref, Template, Tags, Join, Output, GetAtt
from awacs.aws import Allow, Policy, Principal, Statement, Action
import troposphere.iam

S3_PATH='sbma44/traccar/'
try:
    from local_settings import *
except:
    pass
S3_BUCKET=S3_PATH.split('/')[0]

t = Template()
t.set_description('Traccar event handler user for managing traces')

s3policy = troposphere.iam.Policy(
    PolicyName='TraccarS3Policy',
    PolicyDocument= Policy(
        Statement=[
            Statement(
                Sid='S3ListBucket',
                Effect=Allow,
                Action=[
                    Action('s3', 'ListBucket')
                ],
                Resource=['arn:aws:s3:::{}'.format(S3_BUCKET)]
            ),
            Statement(
                Sid='S3PutGet',
                Effect=Allow,
                Action=[
                    Action('s3', 'Get*'),
                    Action('s3', 'Put*')
                ],
                Resource=['arn:aws:s3:::{}*'.format(S3_PATH)]
            ),
            Statement(
                Sid='S3ListAccess',
                Effect=Allow,
                Action=[
                    Action('s3', 'ListObjects'),
                    Action('s3', 'ListObjectsV2')
                ],
                Resource=['arn:aws:s3:::{}*'.format(S3_PATH)]
            )
        ]
    )
)

traccar_user = t.add_resource(troposphere.iam.User('TraccarUser', Policies=[s3policy]))

traccar_user_keys = t.add_resource(troposphere.iam.AccessKey(
    "TraccarUserKeys",
    Status="Active",
    UserName=Ref(traccar_user))
)

# add output to template
t.add_output(Output(
    "AccessKey",
    Value=Ref(traccar_user_keys),
    Description="AWSAccessKeyId",
))
t.add_output(Output(
    "SecretKey",
    Value=GetAtt(traccar_user_keys, "SecretAccessKey"),
    Description="AWSSecretKey",
))

template_json = t.to_json(indent=4)
cfn = boto3.client('cloudformation')
cfn.validate_template(TemplateBody=template_json)

stack ={}
stack['StackName'] = 'TraccarS3User'
stack['TemplateBody'] = template_json
stack['Capabilities'] = ['CAPABILITY_NAMED_IAM']


stack_exists = False
stacks = cfn.list_stacks()['StackSummaries']
for s in stacks:
    if s['StackStatus'] == 'DELETE_COMPLETE':
        continue
    if s['StackName'] == stack['StackName']:
        stack_exists = True

if stack_exists:
    print('Updating {}'.format(stack['StackName']))
    stack_result = cfn.update_stack(**stack)
    waiter = cfn.get_waiter('stack_update_complete')
else:
    print('Creating {}'.format(stack['StackName']))
    stack_result = cfn.create_stack(**stack)
    waiter = cfn.get_waiter('stack_create_complete')
print("...waiting for stack to be ready...")
waiter.wait(StackName=stack['StackName'])