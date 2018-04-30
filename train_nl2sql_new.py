# *- coding: utf-8 -*-
import json
import torch
from sqlnet.utils_new import *
from sqlnet.model.seq2sql import Seq2SQL
from sqlnet.model.sqlnet import SQLNet
import numpy as np
import datetime

import argparse
import logging

if __name__ == '__main__':
    logPath = 'log'
    fileName = str(datetime.datetime.now())
    logging.basicConfig(handlers=[
        logging.FileHandler("{0}/{1}.log".format(logPath, fileName)),
        logging.StreamHandler()
    ], level=logging.WARNING)
    parser = argparse.ArgumentParser()
    parser.add_argument('--toy', action='store_true', 
            help='If set, use small data; used for fast debugging.')
    parser.add_argument('--suffix', type=str, default='',
            help='The suffix at the end of saved model name.')
    parser.add_argument('--ca', action='store_true',
            help='Use conditional attention.')
    parser.add_argument('--dataset', type=int, default=0,
            help='0: original dataset, 1: re-split dataset, 2: Tao Dataset')
    parser.add_argument('--rl', action='store_true',
            help='Use RL for Seq2SQL(requires pretrained model).')
    parser.add_argument('--baseline', action='store_true', 
            help='If set, then train Seq2SQL model; default is SQLNet model.')
    parser.add_argument('--train_emb', action='store_true',
            help='Train word embedding for SQLNet(requires pretrained model).')
    args = parser.parse_args()


    N_word=300
    B_word=42
    if args.toy:
        USE_SMALL=True
        GPU=True
        BATCH_SIZE=10
    else:
        USE_SMALL=True
        GPU=True
        BATCH_SIZE=40
    TRAIN_ENTRY=(True, True, True)  # (AGG, SEL, COND) # TODDO - change last one to False
    TRAIN_AGG, TRAIN_SEL, TRAIN_COND = TRAIN_ENTRY
    learning_rate = 1e-4 if args.rl else 1e-3

    logging.warning('about to load dataset')
    sql_data, table_data, val_sql_data, val_table_data, test_sql_data, test_table_data = load_dataset(args.dataset, use_small=USE_SMALL)
    if args.toy:
        sql_data = sql_data[20:BATCH_SIZE + 20]
        val_sql_data = val_sql_data[20 :BATCH_SIZE + 20]
        # logging.warning('sql_data: {0}'.format(json.dumps(sql_data, indent=4)))

    logging.warning('data loaded')
    word_emb = load_word_emb('glove/glove.%dB.%dd.txt'%(B_word,N_word), \
            load_used=args.train_emb, use_small=USE_SMALL)

    logging.warning('glove loaded')

    if args.baseline:
        model = Seq2SQL(word_emb, N_word=N_word, gpu=GPU,
                trainable_emb = args.train_emb)
        assert not args.train_emb, "Seq2SQL can\'t train embedding."
    else:
        model = SQLNet(word_emb, N_word=N_word, use_ca=args.ca,
                gpu=GPU, trainable_emb = args.train_emb)
        assert not args.rl, "SQLNet can\'t do reinforcement learning."
    optimizer = torch.optim.Adam(model.parameters(),
            lr=learning_rate, weight_decay = 0)
    if args.toy:
        sql_data = sql_data[:BATCH_SIZE]
        val_sql_data = val_sql_data[:BATCH_SIZE]
        # test_sql_data = test_sql_data[:BATCH_SIZE]
    logging.warning('SQLNet loaded')

    if args.train_emb:
        agg_m, sel_m, cond_m, agg_e, sel_e, cond_e = best_model_name(args)
    else:
        agg_m, sel_m, cond_m = best_model_name(args)

    if args.rl or args.train_emb: # Load pretrained model.
        agg_lm, sel_lm, cond_lm = best_model_name(args, for_load=True)
        print "Loading from %s"%agg_lm
        model.agg_pred.load_state_dict(torch.load(agg_lm))
        print "Loading from %s"%sel_lm
        model.sel_pred.load_state_dict(torch.load(sel_lm))
        print "Loading from %s"%cond_lm
        model.cond_pred.load_state_dict(torch.load(cond_lm))
    
    if args.rl:
        best_acc = 0.0
        best_idx = -1
        logging.warning("Init dev acc_qm: %s\n  breakdown on (agg, sel, where): %s\n more specific breakdown %s"% \
                epoch_acc_new(model, BATCH_SIZE, val_sql_data,\
                val_table_data, TRAIN_ENTRY))
        logging.warning("Init dev acc_  : %s"%epoch_exec_acc(
                model, BATCH_SIZE, val_sql_data, val_table_data, DEV_DB))
        torch.save(model.cond_pred.state_dict(), cond_m)
        for i in range(100):
            logging.info('Epoch %d @ %s'%(i+1, datetime.datetime.now()))
            logging.info(' Avg reward = %s'%epoch_reinforce_train(
                model, optimizer, BATCH_SIZE, sql_data, table_data, TRAIN_DB))
            logging.info(' dev acc_qm: %s\n   breakdown result: %s'% epoch_acc(
                model, BATCH_SIZE, val_sql_data, val_table_data, TRAIN_ENTRY))
            exec_acc = epoch_exec_acc(
                    model, BATCH_SIZE, val_sql_data, val_table_data, DEV_DB)
            logging.info(' dev acc_ex: %s', exec_acc)
            if exec_acc[0] > best_acc:
                best_acc = exec_acc[0]
                best_idx = i+1
                torch.save(model.cond_pred.state_dict(),
                        'saved_model/epoch%d.cond_model%s'%(i+1, args.suffix))
                torch.save(model.cond_pred.state_dict(), cond_m)
            logging.info(' Best exec acc = %s, on epoch %s'%(best_acc, best_idx))
    else:
        init_acc = epoch_acc_new(model, BATCH_SIZE,
                val_sql_data, val_table_data, TRAIN_ENTRY)
        logging.warning('init_acc: %s', str(init_acc))
        best_agg_acc = init_acc[1][0]
        best_agg_idx = 0
        best_sel_acc = init_acc[1][1]
        best_sel_idx = 0
        best_cond_acc = init_acc[1][2]
        best_cond_idx = 0
        best_agg_num_acc = init_acc[2][0][0]
        best_agg_num_idx = 0
        best_agg_op_acc = init_acc[2][0][1]
        best_agg_op_idx = 0
        best_sel_num_acc = init_acc[2][1][0]
        best_sel_num_idx = 0
        best_sel_col_acc = init_acc[2][1][1]
        best_sel_col_idx = 0
        best_cond_num_acc = init_acc[2][2][0]
        best_cond_num_idx = 0
        best_cond_col_acc = init_acc[2][2][1]
        best_cond_col_idx = 0
        best_cond_op_acc = init_acc[2][2][2]
        best_cond_op_idx = 0
        logging.warning('Init dev acc_qm: %s\n  breakdown on (agg, sel, where): %s futher breakdown %s' % init_acc)

        if TRAIN_AGG:
            torch.save(model.agg_pred.state_dict(), agg_m)
            if args.train_emb:
                torch.save(model.agg_embed_layer.state_dict(), agg_e)
        if TRAIN_SEL:
            torch.save(model.sel_pred.state_dict(), sel_m)
            if args.train_emb:
                torch.save(model.sel_embed_layer.state_dict(), sel_e)
        if TRAIN_COND:
            torch.save(model.cond_pred.state_dict(), cond_m)
            if args.train_emb:
                torch.save(model.cond_embed_layer.state_dict(), cond_e)
        loss = 100
        # for i in range(100):
        # i = 0
        # while loss > 1:
        
        for i in range(500):
            logging.warning('Epoch %d @ %s'%(i+1, datetime.datetime.now()))
            logging.warning(' Loss = %s'%epoch_train(
                    model, optimizer, BATCH_SIZE, 
                    sql_data, table_data, TRAIN_ENTRY))
            train_acc_tot, train_acc_indiv, train_acc_break = epoch_acc_new(model, BATCH_SIZE, sql_data, table_data, TRAIN_ENTRY)
            logging.warning(' Train acc_qm: %s\n   breakdown result: %s further breakdown: %s'% (train_acc_tot, train_acc_indiv, train_acc_break))
            logging.warning('-------------')
            logging.warning('validation acc!')
            val_acc = epoch_acc_new(model,
                    BATCH_SIZE, val_sql_data, val_table_data, TRAIN_ENTRY)
            logging.warning(' Dev acc_qm: %s\n   breakdown result: %s\n Further breakdown: %s'%val_acc)
            if TRAIN_AGG:
                # logging.warning('val_acc[1][0]: %s', str(val_acc[1][0]))
                # logging.warning('best_agg_acc: %s', str(best_agg_acc))
                if val_acc[1][0] > best_agg_acc:
                    best_agg_acc = val_acc[1][0]
                    best_agg_idx = i + 1
                    torch.save(model.agg_pred.state_dict(),
                        'saved_model/epoch%d.agg_model%s'%(i+1, args.suffix))
                    torch.save(model.agg_pred.state_dict(), agg_m)
                agg_acc = val_acc[2][0]
                if agg_acc[0] > best_agg_num_acc:
                    best_agg_num_acc = agg_acc[0]
                    best_agg_num_idx = i+1
                if agg_acc[1] > best_agg_op_acc:
                    best_agg_op_acc = agg_acc[1]
                    best_agg_op_idx = i+1
                
                # if args.train_emb:
                #     torch.save(model.agg_embed_layer.state_dict(),
                #         'saved_model/epoch%d.agg_embed%s'%(i+1, args.suffix))
                #     torch.save(model.agg_embed_layer.state_dict(), agg_e)
            if TRAIN_SEL:
                if val_acc[1][1] > best_sel_acc:
                    best_sel_acc = val_acc[1][1]
                    best_sel_idx = i + 1
                    torch.save(model.sel_pred.state_dict(),
                        'saved_model/epoch%d.sel_model%s'%(i+1, args.suffix))
                    torch.save(model.sel_pred.state_dict(), sel_m)
                    if args.train_emb:
                        torch.save(model.sel_embed_layer.state_dict(),
                        'saved_model/epoch%d.sel_embed%s'%(i+1, args.suffix))
                        torch.save(model.sel_embed_layer.state_dict(), sel_e)
                sel_acc = val_acc[2][1]
                if sel_acc[0] > best_sel_num_acc:
                    best_sel_num_acc = sel_acc[0]
                    best_sel_num_idx = i+1
                if sel_acc[1] > best_sel_col_acc:
                    best_sel_col_acc = sel_acc[1]
                    best_sel_col_idx = i+1
                
                # if args.train_emb:
                #     torch.save(model.agg_embed_layer.state_dict(),
                #         'saved_model/epoch%d.agg_embed%s'%(i+1, args.suffix))
                #     torch.save(model.agg_embed_layer.state_dict(), agg_e)
            if TRAIN_COND:
                # logging.warning('val_acc[1][2]: %s', str(val_acc[1][2]))
                # logging.warning('best_cond_acc: %s', str(best_cond_acc))
                if val_acc[1][2] > best_cond_acc:
                    best_cond_acc = val_acc[1][2]
                    best_cond_idx = i + 1 
 
                    torch.save(model.cond_pred.state_dict(),
                        'saved_model/epoch%d.cond_model%s'%(i+1, args.suffix))
                    torch.save(model.cond_pred.state_dict(), cond_m)
                    if args.train_emb:
                        torch.save(model.cond_embed_layer.state_dict(),
                        'saved_model/epoch%d.cond_embed%s'%(i+1, args.suffix))
                cond_acc = val_acc[2][2]
                if cond_acc[0] > best_cond_num_acc:
                    best_cond_num_acc = cond_acc[0]
                    best_cond_num_idx = i+1
                if cond_acc[1] > best_cond_op_acc:
                    best_cond_op_acc = cond_acc[1]
                    best_cond_op_idx = i+1
                if cond_acc[2] > best_cond_op_acc:
                    best_cond_val_acc = cond_acc[2]
                    best_cond_val_idx = i+1
  
        logging.warning('Best_agg_acc = %s on epoch %s ', str(best_agg_acc), str(best_agg_idx))
        logging.warning('best_sel_acc = %s on epoch %s ', str(best_sel_acc), str(best_sel_idx))
        logging.warning('best_cond_acc = %s on epoch %s ', str(best_cond_acc), str(best_cond_idx))
        print('\a')
            # print ' Best val acc = %d, on epoch %d individually'% (best_agg_acc, best_sel_acc, best_cond_acc), (best_agg_idx, best_sel_idx, best_cond_idx)
                    # (best_agg_num_acc, best_agg_op_acc, best_sel_num_acc, best_sel_col_acc, best_cond_num_acc, best_cond_col_acc, best_cond_op_acc),
                    # (best_agg_num_idx, best_agg_op_idx, best_sel_num_idx, best_sel_col_idx, best_cond_num_idx, best_cond_col_idx, best_cond_op_idx))
