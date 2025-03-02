#!/bin/bash

# Clear previous configurations
clear

# Load .env variables
set -a
source .env
set +a

# Setup AWS CLI alias
alias awslocal="AWS_ACCESS_KEY_ID=test \
                AWS_SECRET_ACCESS_KEY=test \
                AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION} \
                aws --endpoint-url=http://${LOCALSTACK_HOST:-localhost}:4566"

region=${AWS_DEFAULT_REGION}

echo "Default AWS region: $region"

# **Creating S3 Bucket**
echo "\nCreating S3 bucket: $S3_BUCKET"
awslocal s3api create-bucket --bucket $S3_BUCKET

# **Creating DynamoDB Table**
echo "\nCreating DynamoDB table: $DYNAMODB_TABLE"
awslocal dynamodb create-table \
    --table-name $DYNAMODB_TABLE \
    --attribute-definitions AttributeName=smartpot_id,AttributeType=S \
    --key-schema AttributeName=smartpot_id,KeyType=HASH \
    --provisioned-throughput ReadCapacityUnits=1,WriteCapacityUnits=1 \
    --region $region

# **Creating SQS Queues**
echo "\nCreating SQS queues"
SmartPotQueueURL=$(awslocal sqs create-queue --queue-name $SQS_IRRIGATION_QUEUE --region $region | jq -r '.QueueUrl')
SmartPotQueueARN=$(awslocal sqs get-queue-attributes --queue-url $SmartPotQueueURL --attribute-name QueueArn | jq -r '.Attributes.QueueArn')
echo "SmartPotQueueARN: $SmartPotQueueARN"

AlertsQueueURL=$(awslocal sqs create-queue --queue-name $SQS_ALERTS_QUEUE --region $region | jq -r '.QueueUrl')
AlertsQueueARN=$(awslocal sqs get-queue-attributes --queue-url $AlertsQueueURL --attribute-name QueueArn | jq -r '.Attributes.QueueArn')
echo "AlertsQueueARN: $AlertsQueueARN"

# **Creating Kinesis Stream**
echo "\nCreating Kinesis stream: $KINESIS_STREAM"
awslocal kinesis create-stream --stream-name $KINESIS_STREAM --shard-count 1 --region $region
KinesisStreamARN=$(awslocal kinesis describe-stream --stream-name $KINESIS_STREAM --region $region | jq -r '.StreamDescription.StreamARN')
echo "KinesisStreamARN: $KinesisStreamARN"

# **Creating IAM Role for Lambda**
echo "\nCreating IAM Role for Lambda"
Role=$(awslocal iam create-role --role-name $IAM_ROLE_NAME --assume-role-policy-document file://./roles/lambda_role.json)
RoleARN=$(echo "$Role" | jq -r '.Role.Arn')
echo "RoleARN: $RoleARN"

awslocal iam attach-role-policy --role-name $IAM_ROLE_NAME --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaKinesisExecutionRole

# **Deploying Lambda Functions**
echo "\nCreating Lambda Functions"

mkdir -p ./tmpZips

declare -A lambda_functions=(
    ["processSensorData"]="processSensorData"
    ["handleAlerts"]="handleAlerts"
    ["irrigateNow"]="irrigateNow"
    ["createDailyReport"]="createDailyReport"
    ["createManualReport"]="createManualReport"
    ["getReport"]="getReport"
    ["getAllReports"]="getAllReports"
    ["getLatestData"]="getLatestData"
)

for function in "${!lambda_functions[@]}"; do
    echo "Creating $function Lambda"

    if [ "$function" == "irrigateNow" ]; then
        # ✅ Creazione speciale per irrigateNow con pacchetto e librerie
        echo "📦 Installing dependencies for irrigateNow..."
        mkdir -p ./tmpZips/package
        pip install paho-mqtt -t ./tmpZips/package/
        cp ./lambdas/$function.py ./tmpZips/package/
        
        # Crea il pacchetto ZIP
        cd ./tmpZips/package
        zip -r ../$function.zip .
        cd ../..

    else
        # ✅ Creazione normale per le altre Lambda
        zip -j ./tmpZips/$function.zip ./lambdas/$function.py
    fi

    if [ "$function" == "handleAlerts" ]; then
        # ✅ Aggiunge le variabili di Telegram SOLO per handleAlerts
        awslocal lambda create-function --function-name $function \
            --zip-file fileb://./tmpZips/$function.zip \
            --handler $function.lambda_handler \
            --runtime python3.12 \
            --role $RoleARN \
            --environment "Variables={TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN,TELEGRAM_CHAT_ID=$TELEGRAM_CHAT_ID}" \
            --no-cli-pager
    else
        # ✅ Crea le altre Lambda SENZA le variabili Telegram
        awslocal lambda create-function --function-name $function \
            --zip-file fileb://./tmpZips/$function.zip \
            --handler $function.lambda_handler \
            --runtime python3.12 \
            --role $RoleARN \
            --no-cli-pager
    fi
done


# **Setting Kinesis Trigger for processSensorData**
awslocal lambda create-event-source-mapping \
    --function-name processSensorData \
    --event-source $KinesisStreamARN \
    --batch-size 5 \
    --starting-position LATEST

# **Setting SQS Trigger for handleAlerts**
awslocal lambda create-event-source-mapping \
    --function-name handleAlerts \
    --event-source-arn $AlertsQueueARN \
    --batch-size 5

awslocal lambda create-event-source-mapping \
    --function-name irrigateNow \
    --event-source-arn $SmartPotQueueARN \
    --batch-size 5

# **Creating EventBridge Rule for Daily Report**
echo "\nCreating EventBridge Rule for Daily Report"

awslocal events put-rule \
    --name scheduled-daily-report \
    --schedule-expression 'cron(30 12 * * ? *)' \
    --region $region

awslocal lambda add-permission \
    --function-name createDailyReport \
    --statement-id scheduled-daily-report-event \
    --action 'lambda:InvokeFunction' \
    --principal events.amazonaws.com \
    --source-arn arn:aws:events:$region:000000000000:rule/scheduled-daily-report

awslocal events put-targets \
    --rule scheduled-daily-report \
    --targets file://targets/target_report.json \
    --region $region

# Create API Gateway
echo "\nCreating API Gateway"
output_api=$(awslocal apigateway create-rest-api --name 'SmartPotSystem API Gateway' --region $region)
api_id=$(echo $output_api | jq -r '.id')

output_parent=$(awslocal apigateway get-resources --rest-api-id $api_id --region $region)
parent_id=$(echo $output_parent | jq -r '.items[0].id')

declare -A api_endpoints=(
    ["getLatestData"]="getLatestData"
    ["getAllReports"]="getAllReports"
    ["getReport"]="getReport"
    ["createManualReport"]="createManualReport"
    ["irrigateNow"]="irrigateNow"
)

for endpoint in "${!api_endpoints[@]}"; do
    echo "Creating API Gateway resource for $endpoint"
    output_resource=$(awslocal apigateway create-resource --rest-api-id $api_id --parent-id $parent_id --path-part $endpoint --region $region)
    resource_id=$(echo $output_resource | jq -r '.id')

    # Crea il metodo GET per tutti gli endpoint tranne "irrigateNow" che deve usare POST
    if [ "$endpoint" == "irrigateNow" || "$endpoint" == "createManualReport" ]; then
        method="POST"
    else
        method="GET"
    fi

    awslocal apigateway put-method \
        --rest-api-id $api_id \
        --resource-id $resource_id \
        --http-method $method \
        --authorization-type "NONE" \
        --region $region

    awslocal apigateway put-integration \
        --rest-api-id $api_id \
        --resource-id $resource_id \
        --http-method $method \
        --type AWS_PROXY \
        --integration-http-method POST \
        --uri "arn:aws:apigateway:$region:lambda:path/2015-03-31/functions/${api_endpoints[$endpoint]}/invocations" \
        --passthrough-behavior WHEN_NO_MATCH
done

# Deploy API Gateway
echo "\nDeploying API Gateway"
awslocal apigateway create-deployment \
    --rest-api-id $api_id \
    --stage-name test \
    --region $region

AWS_GATEWAY_URL="http://localhost:4566/_aws/execute-api/$api_id/test/"
echo "\n\nAPI Gateway URL: $AWS_GATEWAY_URL\n\n"
echo "AWS_GATEWAY_URL=$AWS_GATEWAY_URL" >> ./.env

# Grant API Gateway permissions to invoke Lambda functions
echo "\nGranting API Gateway permissions to invoke Lambda functions"

for function_name in "${api_endpoints[@]}"; do
    echo "Granting permission to function: $function_name"
    awslocal lambda add-permission \
        --function-name $function_name \
        --statement-id "AllowAPIGatewayInvoke-$function_name" \
        --action lambda:InvokeFunction \
        --principal apigateway.amazonaws.com \
        --source-arn "arn:aws:execute-api:$region:*:$api_id/test/*/$function_name"
done


# **Deploy API Gateway**
echo "\nDeploying API Gateway"
awslocal apigateway create-deployment --rest-api-id $api_id --stage-name test --region $region

AWS_GATEWAY_URL="http://localhost:4566/_aws/execute-api/$api_id/test/"
echo "\nAPI Gateway URL: $AWS_GATEWAY_URL"
echo "AWS_GATEWAY_URL=$AWS_GATEWAY_URL" >> .env


# **Cleaning up**
rm -r ./tmpZips/*
rm -f ./tmpZips/.DS_Store
rmdir ./tmpZips

# **Populate DynamoDB**
echo "\nPopulating DynamoDB"
python3 ./usefulScripts/populateDB.py
